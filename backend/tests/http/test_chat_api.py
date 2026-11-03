"""问答 API 的 SSE 协议测试（不连数据库、不调 LLM）。

守的是 SSE 帧格式与流式契约：事件名、data 负载结构、响应头、
以及"done 事件不带 content 也不能让连接被截断"这条历史回归。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.fakes import RecordingGraph, make_source, token_event, tool_update_event

CHAT = "/api/v1/chat"
CONVERSATIONS = "/api/v1/conversations"


def _frames(body: str) -> list[tuple[str, str]]:
    """把 SSE 响应体解析成 (event_name, data) 列表。"""

    frames: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        name: str = ""
        data: str = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if name:
            frames.append((name, data))
    return frames


def _payload(body: str, event_name: str) -> dict:
    """取出指定事件的 data 负载。"""

    return json.loads(next(data for name, data in _frames(body) if name == event_name))


def test_chat_requires_auth(api_client: TestClient, graph: RecordingGraph) -> None:
    """未登录问答返回 401。"""

    assert api_client.post(CHAT, json={"content": "你好"}).status_code == 401


def test_chat_rejects_empty_content(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """空提问返回 422，避免把空消息写进历史。"""

    response = api_client.post(CHAT, json={"content": ""}, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["code"] == 1001


def test_chat_returns_event_stream_headers(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """SSE 响应头必须禁止缓冲与缓存，否则前端会攒着一批才显示。"""

    graph.events = [token_event("你好")]

    response = api_client.post(CHAT, json={"content": "你好"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"


def test_chat_streams_conversation_id_then_tokens_then_done(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """帧顺序：conversation_id → token... → done。"""

    graph.events = [token_event("RAG 是"), token_event("检索增强生成")]

    response = api_client.post(CHAT, json={"content": "什么是 RAG？"}, headers=auth_headers)

    names = [name for name, _ in _frames(response.text)]
    assert names[0] == "conversation_id"
    assert names[-1] == "done"
    assert names.count("token") == 2


def test_chat_done_frame_has_null_content(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """回归：done 事件只有 type 没有 content。

    路由里若用 event["content"] 取值会抛 KeyError，导致响应在结尾被截断 ——
    前端表现为"回答显示完了但一直不结束"。
    """

    graph.events = [token_event("回答")]

    response = api_client.post(CHAT, json={"content": "问题"}, headers=auth_headers)

    done_frames = [data for name, data in _frames(response.text) if name == "done"]
    assert done_frames == ['{"type": "done", "content": null}']


def test_chat_token_frames_carry_text(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """token 帧的 data 里带上增量文本，中文不被转义。"""

    graph.events = [token_event("你好"), token_event("，世界")]

    response = api_client.post(CHAT, json={"content": "打招呼"}, headers=auth_headers)

    token_data = [data for name, data in _frames(response.text) if name == "token"]
    assert token_data[0] == '{"type": "token", "content": "你好"}'
    assert '"content": "，世界"' in token_data[1]


def test_chat_emits_sources_frame_when_retrieved(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """有检索命中时在正文后补一帧 sources。"""

    graph.hits.append(make_source(1, 0))
    graph.events = [token_event("基于文档的回答")]

    response = api_client.post(CHAT, json={"content": "问题"}, headers=auth_headers)

    frames = _frames(response.text)
    names = [name for name, _ in frames]
    assert "sources" in names
    assert names.index("sources") > names.index("token")
    assert '"document_id": 1' in frames[names.index("sources")][1]


def test_chat_creates_conversation_and_persists_messages(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """一轮问答后会话与两条消息都可通过 API 查到。"""

    graph.events = [token_event("回答内容")]

    response = api_client.post(CHAT, json={"content": "第一个问题"}, headers=auth_headers)
    conversation_id: int = _payload(response.text, "conversation_id")["content"]

    conversations = api_client.get(CONVERSATIONS, headers=auth_headers).json()["data"]
    assert conversations["total"] == 1
    assert conversations["items"][0]["id"] == conversation_id

    messages = api_client.get(
        f"{CONVERSATIONS}/{conversation_id}/messages", headers=auth_headers
    ).json()["data"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "第一个问题"),
        ("assistant", "回答内容"),
    ]


def test_chat_continues_existing_conversation(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """传入已有会话 ID 时续写，且历史进入 Agent 上下文。"""

    graph.events = [token_event("第一轮回答")]
    first = api_client.post(CHAT, json={"content": "第一个问题"}, headers=auth_headers)
    conversation_id: int = _payload(first.text, "conversation_id")["content"]

    graph.events = [token_event("第二轮回答")]
    api_client.post(
        CHAT,
        json={"content": "第二个问题", "conversation_id": conversation_id},
        headers=auth_headers,
    )

    payload = graph.payloads[-1]["messages"]
    assert [type(item).__name__ for item in payload] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert payload[-1].content == "第二个问题"


@pytest.mark.xfail(
    strict=True,
    reason="已知缺陷：会话归属校验发生在生成器内，响应已开始，异常无法翻译成 404",
)
def test_chat_rejects_other_users_conversation(
    lenient_client: TestClient, graph: RecordingGraph
) -> None:
    """越权往他人会话发消息应返回 404，目前返回的是 500。

    根因（实测）：``ChatService.stream_chat`` 是一个生成器，``_get_or_create_conversation``
    在**响应已经开始之后**才执行，此时抛出的 HTTPException 无法再修改状态码，
    FastAPI 只能把它降级成 500；``APP_DEBUG=true`` 时响应体还会带上完整堆栈。

    修法：把会话解析提到创建 ``StreamingResponse`` 之前（路由里先做一次
    归属校验），或让服务层提供一个非懒执行的入口方法。
    """

    graph.events = [token_event("回答")]
    alice_headers = _login_headers(lenient_client, "alice")
    first = lenient_client.post(CHAT, json={"content": "问题"}, headers=alice_headers)
    conversation_id: int = _payload(first.text, "conversation_id")["content"]

    response = lenient_client.post(
        CHAT,
        json={"content": "偷看", "conversation_id": conversation_id},
        headers=_login_headers(lenient_client, "bob"),
    )

    assert response.status_code == 404


def test_foreign_conversation_receives_no_messages_even_when_rejected(
    lenient_client: TestClient, graph: RecordingGraph
) -> None:
    """越权请求被拒绝后，对方会话里不能留下任何消息。

    这条是**当前就能成立**的安全底线：即便状态码处理有问题，
    数据也不允许越权写入。
    """

    graph.events = [token_event("回答")]
    alice_headers = _login_headers(lenient_client, "alice")
    first = lenient_client.post(CHAT, json={"content": "问题"}, headers=alice_headers)
    conversation_id: int = _payload(first.text, "conversation_id")["content"]

    lenient_client.post(
        CHAT,
        json={"content": "偷看", "conversation_id": conversation_id},
        headers=_login_headers(lenient_client, "bob"),
    )

    messages = lenient_client.get(
        f"{CONVERSATIONS}/{conversation_id}/messages", headers=alice_headers
    ).json()["data"]
    assert [m["content"] for m in messages] == [
        "问题",
        "回答",
    ]  # 只有 alice 自己那一轮，没有 bob 的 "偷看"


def _login_headers(client: TestClient, username: str) -> dict[str, str]:
    """注册并登录指定用户，返回请求头。"""

    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_chat_filters_tool_intermediate_output(
    api_client: TestClient, auth_headers: dict[str, str], graph: RecordingGraph
) -> None:
    """回归：工具内部 LLM 产出的 JSON 中间产物不能出现在 token 帧里。"""

    graph.events = [
        tool_update_event("search_knowledge"),
        token_event('```json\n["改写查询"]\n```', node="tools"),
        token_event("真正的回答"),
    ]

    response = api_client.post(CHAT, json={"content": "问题"}, headers=auth_headers)

    tokens = [data for name, data in _frames(response.text) if name == "token"]
    assert len(tokens) == 1
    assert "真正的回答" in tokens[0]
