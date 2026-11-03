"""SSE 事件流回归测试。

覆盖一个曾经真实发生过的缺陷：`done` 事件只带 type、不带 content，
而路由层无条件读 `event["content"]`，导致流末尾抛 KeyError、
整个 SSE 连接被截断，客户端永远收不到 done。

这里 monkeypatch 掉 ChatService.stream_chat，不依赖真实 LLM，
只校验 HTTP 层把 service 产出的每一种事件都完整透传出去。
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agent.agent import ChatAgentBundle
from app.service.chat_service import ChatService


def _register_and_login(client: TestClient) -> str:
    """注册并登录，返回 Bearer token。"""

    username: str = "sse_tester"
    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    assert resp.status_code == 200
    return str(resp.json()["data"]["access_token"])


def _fake_stream_chat(self, user, chat_in):
    """按真实顺序产出四类事件，其中 done 不带 content。"""

    yield {"type": "conversation_id", "content": 1}
    yield {"type": "token", "content": "你好"}
    yield {"type": "token", "content": "世界"}
    yield {
        "type": "sources",
        "content": [
            {
                "document_id": 7,
                "document_title": "os_thread",
                "chunk_index": 2,
                "snippet": "线程是 CPU 调度的基本单位",
                "score": 0.83,
            }
        ],
    }
    yield {"type": "done"}


def test_chat_stream_passes_every_event(client: TestClient, monkeypatch) -> None:
    """四种事件都要完整到达客户端，done 之后流正常结束。"""

    monkeypatch.setattr(ChatService, "stream_chat", _fake_stream_chat)
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/v1/chat", headers=headers, json={"content": "线程是什么"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    kinds: list[str] = [str(e["type"]) for e in events]
    assert kinds == ["conversation_id", "token", "token", "sources", "done"], kinds

    # done 事件必须存在，且 content 为 null 而不是缺字段
    done_event: dict = events[-1]
    assert done_event["type"] == "done"
    assert done_event["content"] is None

    # sources 的字段要原样带出去，前端才能展示精确引用
    sources: list[dict] = events[3]["content"]
    assert sources[0]["document_id"] == 7
    assert sources[0]["chunk_index"] == 2


def test_chat_stream_keeps_going_without_sources(client: TestClient, monkeypatch) -> None:
    """没有命中任何文档时，sources 事件可以不出现，但 done 必须出现。"""

    def _no_source_stream(self, user, chat_in):
        yield {"type": "conversation_id", "content": 1}
        yield {"type": "token", "content": "通用回答"}
        yield {"type": "done"}

    monkeypatch.setattr(ChatService, "stream_chat", _no_source_stream)
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/v1/chat", headers=headers, json={"content": "你好"})
    assert resp.status_code == 200

    events: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    kinds: list[str] = [str(e["type"]) for e in events]
    assert kinds == ["conversation_id", "token", "done"], kinds


class _StubAgent:
    """按真实事件顺序回放一次 Agent 执行。

    其中 tools 节点夹带了查询改写的原始 JSON 输出 —— 这是工具内部自己发起的
    LLM 调用，同样会以 messages 事件流出，必须被服务层按节点名剔除。
    """

    def stream(self, _inputs: object, stream_mode: object = None):
        yield ("messages", (AIMessageChunk(content=""), {"langgraph_node": "model"}))
        yield ("messages", (AIMessageChunk(content="```json\n[\n"), {"langgraph_node": "tools"}))
        yield (
            "messages",
            (
                AIMessageChunk(content='    "线程与进程的差异"\n]\n```'),
                {"langgraph_node": "tools"},
            ),
        )
        yield (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="检索结果", tool_call_id="call_1", name="search_knowledge"
                        )
                    ]
                }
            },
        )
        yield ("messages", (AIMessageChunk(content="线程是"), {"langgraph_node": "model"}))
        yield (
            "messages",
            (AIMessageChunk(content=" CPU 调度的基本单位。"), {"langgraph_node": "model"}),
        )


def test_chat_stream_drops_tool_node_llm_output(client: TestClient, monkeypatch) -> None:
    """工具节点内部的 LLM 输出（如查询改写的 JSON）不得混进回答 token。

    回归背景：search_knowledge 工具内部会调用 LLM 做查询改写，而
    stream_mode="messages" 会捕获图内所有 LLM 的 token。若只按消息类型过滤，
    改写结果会以 ```json [...] 的形式出现在回答开头，并被一起落库。
    """

    monkeypatch.setattr(
        "app.service.chat_service.create_chat_agent",
        lambda _session, _user_id: ChatAgentBundle(agent=_StubAgent(), retrieved_hits=[]),
    )

    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/v1/chat", headers=headers, json={"content": "线程是什么"})
    assert resp.status_code == 200

    events: list[dict] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))

    answer: str = "".join(str(e["content"]) for e in events if e["type"] == "token")
    assert answer == "线程是 CPU 调度的基本单位。", answer
    assert "json" not in answer
    assert "改写" not in answer

    # done 必须照样到达，工具轨迹也不能因为过滤而丢失
    assert events[-1]["type"] == "done"
