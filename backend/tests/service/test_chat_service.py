"""问答服务测试（内存库 + 假 Agent 图，不需要数据库、LLM、Redis）。

这是产品的核心链路，也是此前唯一完全没被单测覆盖的部分：
用户提问 → 取历史 → 存用户消息 → Agent 流式执行 → 抽取 token → 存回答 → 写引用来源。

测试策略：用 ``RecordingGraph`` 回放 ``(stream_mode, event)`` 事件对，
精确复现 LangGraph 真实的流式输出形状（包括工具内部 LLM 调用产生的中间产物），
从而在不调用任何模型的前提下验证抽取与过滤逻辑。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.agent.agent import ChatAgentBundle
from app.core.cache import history_key
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.service import chat_service as chat_service_module
from app.service.chat_service import ChatService
from tests.fakes import (
    FakeCache,
    FakeConversationRepository,
    FakeMessageRepository,
    FakeSession,
    MemoryStore,
    RecordingGraph,
    make_source,
    token_event,
    tool_update_event,
)


def _stream(
    service: ChatService,
    user: User,
    content: str = "什么是 RAG？",
    conversation_id: int | None = None,
) -> list[dict[str, object]]:
    """消费流式问答，返回全部事件。"""

    request = ChatRequest(content=content, conversation_id=conversation_id)
    return list(service.stream_chat(user, request))


def _tokens(events: list[dict[str, object]]) -> str:
    """把 token 事件拼成完整回答。"""

    return "".join(str(event["content"]) for event in events if event["type"] == "token")


@pytest.fixture()
def graph() -> RecordingGraph:
    """可编排的假 Agent 图。"""

    return RecordingGraph()


@pytest.fixture()
def service(
    fake_repositories: MemoryStore,
    fake_session: FakeSession,
    fake_cache: FakeCache,
    monkeypatch: pytest.MonkeyPatch,
    graph: RecordingGraph,
) -> ChatService:
    """问答服务实例，Agent 工厂被替换为假图。"""

    bundle = ChatAgentBundle(agent=cast(Any, graph), retrieved_hits=graph.hits)
    monkeypatch.setattr(chat_service_module, "create_chat_agent", lambda session, user_id: bundle)
    return ChatService(cast(Any, fake_session))


# ── 流式主流程 ────────────────────────────────────────────────


def test_stream_creates_conversation_and_saves_messages(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """新会话：返回会话 ID、拼接 token、落库用户与助手两条消息。"""

    # 完整一轮：先由工具检索（updates），再流式产出回答（messages）
    graph.events = [
        tool_update_event("search_knowledge"),
        token_event("RAG 是"),
        token_event("检索增强生成"),
        token_event("。"),
    ]

    events = _stream(service, alice)

    assert events[0]["type"] == "conversation_id"
    assert events[-1] == {"type": "done"}
    assert _tokens(events) == "RAG 是检索增强生成。"
    assert [(m.role, m.content) for m in store.messages.values()] == [
        ("user", "什么是 RAG？"),
        ("assistant", "RAG 是检索增强生成。"),
    ]


def test_stream_reports_conversation_id_before_tokens(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """会话 ID 必须先于 token 下发，前端才能在第一个字到达时就确定会话。"""

    graph.events = [token_event("回答")]

    events = _stream(service, alice)

    types = [event["type"] for event in events]
    assert types.index("conversation_id") < types.index("token")
    assert events[0]["content"] == next(iter(store.conversations))


def test_stream_commits_so_updated_at_is_refreshed(
    service: ChatService, graph: RecordingGraph, alice: User, fake_session: FakeSession
) -> None:
    """提问后必须提交一次，否则会话的 updated_at 不更新、无法置顶。"""

    graph.events = [token_event("回答")]

    _stream(service, alice)

    assert fake_session.commit_count == 1


def test_stream_passes_current_question_to_agent(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """当前提问作为最后一条 HumanMessage 传给 Agent。"""

    graph.events = [token_event("回答")]

    _stream(service, alice, content="今年的政策是什么？")

    payload = graph.payloads[0]["messages"]
    assert payload[-1].content == "今年的政策是什么？"


def test_stream_uses_hybrid_stream_mode(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """必须同时订阅 updates（工具轨迹）与 messages（token）。"""

    graph.events = [token_event("回答")]

    _stream(service, alice)

    assert set(graph.stream_modes[0]) == {"updates", "messages"}


def test_stream_saves_empty_answer_without_crashing(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """模型未产出任何 token 时仍要写入一条空回答并正常结束，而不是抛异常。"""

    graph.events = []

    events = _stream(service, alice)

    assert events[-1] == {"type": "done"}
    assistant = next(m for m in store.messages.values() if m.role == "assistant")
    assert assistant.content == ""


# ── 会话归属与标题 ────────────────────────────────────────────


def test_stream_rejects_other_users_conversation(
    service: ChatService, graph: RecordingGraph, bob: User, alice_conversation: Conversation
) -> None:
    """越权往他人会话发消息必须被拒绝，且不产生任何消息。"""

    graph.events = [token_event("偷看")]

    with pytest.raises(Exception, match="会话不存在"):
        _stream(service, bob, conversation_id=alice_conversation.id)


def test_existing_conversation_is_reused(
    service: ChatService,
    graph: RecordingGraph,
    alice: User,
    alice_conversation: Conversation,
    store: MemoryStore,
) -> None:
    """指定已有会话时复用，不再新建，也不改标题。"""

    graph.events = [token_event("继续回答")]

    events = _stream(service, alice, content="接着上一轮", conversation_id=alice_conversation.id)

    assert events[0]["content"] == alice_conversation.id
    assert len(store.conversations) == 1
    assert alice_conversation.title == "alice 的会话"


def test_new_conversation_titled_from_question(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """新会话用首条提问命名，省去用户手动改名。"""

    graph.events = [token_event("回答")]

    _stream(service, alice, content="什么是 RAG？")

    assert next(iter(store.conversations.values())).title == "什么是 RAG？"


def test_new_conversation_title_truncated_to_30_chars(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """超长提问截断到 30 字，避免标题撑破侧边栏。"""

    graph.events = [token_event("回答")]

    _stream(service, alice, content="问" * 50)

    assert next(iter(store.conversations.values())).title == "问" * 30


def test_untitled_conversation_gets_renamed_on_first_question(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """仍是默认名的会话，首轮提问后应被命名。"""

    conversation: Conversation = FakeConversationRepository().create(
        user_id=alice.id, title="新对话"
    )
    graph.events = [token_event("回答")]

    _stream(service, alice, content="真正的第一个问题", conversation_id=conversation.id)

    assert conversation.title == "真正的第一个问题"


# ── token 抽取与过滤（历史回归）───────────────────────────────


def test_tool_internal_llm_output_is_filtered(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """回归：工具内部 LLM 调用（如查询改写）产生的中间产物不能当成回答。

    现象是回答开头多出一段 ```json [...]```，根因是这些调用同样以 messages
    事件流出，只能按 langgraph_node 过滤。
    """

    graph.events = [
        token_event('```json\n["改写后的查询"]\n```', node="tools"),
        token_event("这是最终回答"),
    ]

    assert _tokens(_stream(service, alice)) == "这是最终回答"


def test_tool_call_arguments_are_not_streamed(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """模型发起工具调用时的输出（tool_calls）不是回答内容。"""

    tool_call_chunk = AIMessageChunk(
        content="正在检索",
        tool_calls=[{"name": "search_knowledge", "args": {"query": "x"}, "id": "c1"}],
    )
    graph.events = [
        ("messages", (tool_call_chunk, {"langgraph_node": "model"})),
        token_event("最终回答"),
    ]

    assert _tokens(_stream(service, alice)) == "最终回答"


def test_legacy_tool_calls_in_additional_kwargs_are_not_streamed(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """部分模型把工具调用放在 additional_kwargs 里，同样要过滤。"""

    legacy = AIMessage(
        content="正在检索",
        additional_kwargs={"tool_calls": [{"id": "c1", "function": {"name": "search"}}]},
    )
    graph.events = [
        ("messages", (legacy, {"langgraph_node": "model"})),
        token_event("最终回答"),
    ]

    assert _tokens(_stream(service, alice)) == "最终回答"


def test_non_string_content_is_ignored(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """多模态 content（列表结构）不能直接拼进回答，否则前端拿到字典。"""

    multimodal = AIMessageChunk(content=[{"type": "text", "text": "片段"}])
    graph.events = [
        ("messages", (multimodal, {"langgraph_node": "model"})),
        token_event("纯文本回答"),
    ]

    assert _tokens(_stream(service, alice)) == "纯文本回答"


def test_extract_token_records_seen_nodes() -> None:
    """节点名会被记录下来，用于排查"为什么一个字都没输出"。"""

    seen: set[str] = set()
    ChatService._extract_token((AIMessageChunk(content="x"), {"langgraph_node": "tools"}), seen)

    assert seen == {"tools"}


def test_extract_token_keeps_chunk_without_node_metadata() -> None:
    """缺少 langgraph_node 的元数据时不过滤，避免误伤。"""

    chunk: str | None = ChatService._extract_token((AIMessageChunk(content="回答"), {}), set())

    assert chunk == "回答"


def test_collect_tool_names_only_reads_tools_node() -> None:
    """工具名只从 tools 节点收集，其他节点的消息不算。"""

    calls: list[str] = []
    ChatService._collect_tool_names(
        {"model": {"messages": [ToolMessage(content="x", name="误入", tool_call_id="1")]}},
        calls,
    )
    ChatService._collect_tool_names(
        tool_update_event("search_knowledge", "list_documents")[1], calls
    )

    assert calls == ["search_knowledge", "list_documents"]


# ── 引用来源 ──────────────────────────────────────────────────


def test_sources_are_deduped_and_emitted(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """引用来源按 (文档 ID, 分块序号) 去重，并保持首次命中顺序。"""

    graph.hits.extend([make_source(1, 0), make_source(1, 0), make_source(2, 3), make_source(1, 1)])
    graph.events = [token_event("回答")]

    events = _stream(service, alice)

    payload = next(event["content"] for event in events if event["type"] == "sources")
    assert [(item["document_id"], item["chunk_index"]) for item in payload] == [
        (1, 0),
        (2, 3),
        (1, 1),
    ]
    assistant = next(m for m in store.messages.values() if m.role == "assistant")
    assert len(assistant.sources or []) == 3


def test_no_sources_means_no_sources_event(
    service: ChatService, graph: RecordingGraph, alice: User, store: MemoryStore
) -> None:
    """没有检索命中时不下发 sources 事件，落库字段为 None。"""

    graph.events = [token_event("你好，我是 DocuMind。")]

    events = _stream(service, alice)

    assert all(event["type"] != "sources" for event in events)
    assistant = next(m for m in store.messages.values() if m.role == "assistant")
    assert assistant.sources is None


def test_sources_event_comes_after_tokens(
    service: ChatService, graph: RecordingGraph, alice: User
) -> None:
    """引用来源在正文之后下发，前端可先渲染回答再补引用。"""

    graph.hits.append(make_source(1, 0))
    graph.events = [token_event("回答")]

    types = [event["type"] for event in _stream(service, alice)]

    assert types.index("sources") > types.index("token")
    assert types[-1] == "done"


# ── 历史 ──────────────────────────────────────────────────────


def test_history_is_loaded_and_passed_to_agent(
    service: ChatService, graph: RecordingGraph, alice: User, alice_conversation: Conversation
) -> None:
    """历史消息以 Human/AI 消息形式放在当前提问之前。"""

    messages = FakeMessageRepository()
    messages.create(alice_conversation.id, "user", "上一轮提问")
    messages.create(alice_conversation.id, "assistant", "上一轮回答")
    graph.events = [token_event("回答")]

    _stream(service, alice, content="这一轮", conversation_id=alice_conversation.id)

    payload = graph.payloads[0]["messages"]
    assert [type(item).__name__ for item in payload] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert payload[0].content == "上一轮提问"
    assert payload[-1].content == "这一轮"


def test_history_is_capped_at_ten_messages(
    service: ChatService, graph: RecordingGraph, alice: User, alice_conversation: Conversation
) -> None:
    """历史只取最近 10 条，避免上下文无限增长推高成本。"""

    messages = FakeMessageRepository()
    for index in range(12):
        messages.create(alice_conversation.id, "user", f"第{index}条")
    graph.events = [token_event("回答")]

    _stream(service, alice, conversation_id=alice_conversation.id)

    payload = graph.payloads[0]["messages"]
    assert len(payload) == 11  # 10 条历史 + 当前提问
    assert payload[0].content == "第2条"


def test_history_cache_hit_avoids_database(
    service: ChatService,
    graph: RecordingGraph,
    alice: User,
    alice_conversation: Conversation,
    fake_cache: FakeCache,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """命中历史缓存时不应再查库。"""

    fake_cache.data[history_key(alice_conversation.id)] = [
        {"role": "user", "content": "缓存中的历史"}
    ]
    monkeypatch.setattr(
        FakeMessageRepository,
        "list_by_conversation_id",
        lambda self, conversation_id: (_ for _ in ()).throw(AssertionError("命中缓存时不应再查库")),
    )
    graph.events = [token_event("回答")]

    _stream(service, alice, conversation_id=alice_conversation.id)

    assert graph.payloads[0]["messages"][0].content == "缓存中的历史"


def test_history_cache_is_refreshed_after_each_round(
    service: ChatService, graph: RecordingGraph, alice: User, fake_cache: FakeCache
) -> None:
    """每轮结束把问答追加进缓存，下一轮省掉一次查询。"""

    graph.events = [token_event("回答")]

    events = _stream(service, alice, content="新问题")

    conversation_id = events[0]["content"]
    assert fake_cache.data[history_key(cast(int, conversation_id))] == [
        {"role": "user", "content": "新问题"},
        {"role": "assistant", "content": "回答"},
    ]


def test_to_messages_ignores_unknown_roles() -> None:
    """历史里出现未知角色（如 tool）时跳过，而不是抛异常。"""

    history = ChatService._to_messages(
        [
            {"role": "user", "content": "问"},
            {"role": "tool", "content": "工具输出"},
            {"role": "assistant", "content": "答"},
        ]
    )

    assert [type(item).__name__ for item in history] == ["HumanMessage", "AIMessage"]
