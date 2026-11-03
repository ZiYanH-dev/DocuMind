"""会话 API 的 HTTP 行为测试（不连数据库）。

重点守两条：统一响应信封 + 跨用户越权返回 404（而不是 403，
避免通过状态码探测"某个会话 ID 是否存在"）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

CONVERSATIONS = "/api/v1/conversations"


def _login_headers(client: TestClient, username: str) -> dict[str, str]:
    """注册并登录指定用户，返回请求头。"""

    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


# ── 创建与列表 ────────────────────────────────────────────────


def test_create_conversation_returns_envelope(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """创建会话返回信封与数据。"""

    response = api_client.post(CONVERSATIONS, json={"title": "我的会话"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["title"] == "我的会话"
    assert body["data"]["id"] > 0


def test_create_conversation_uses_default_title(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """不传标题时使用默认值，而不是报 422。"""

    response = api_client.post(CONVERSATIONS, json={}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["title"] == "新对话"


def test_list_conversations_returns_own_only(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """列表只包含自己的会话。"""

    api_client.post(CONVERSATIONS, json={"title": "A"}, headers=auth_headers)
    other = _login_headers(api_client, "bob")
    api_client.post(CONVERSATIONS, json={"title": "B"}, headers=other)

    body = api_client.get(CONVERSATIONS, headers=auth_headers).json()

    assert body["data"]["total"] == 1
    assert [item["title"] for item in body["data"]["items"]] == ["A"]


def test_list_conversations_pagination(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """分页参数通过查询串传递并生效。"""

    for index in range(3):
        api_client.post(CONVERSATIONS, json={"title": f"会话{index}"}, headers=auth_headers)

    body = api_client.get(f"{CONVERSATIONS}?skip=0&limit=2", headers=auth_headers).json()

    assert len(body["data"]["items"]) == 2
    assert body["data"]["total"] == 3


# ── 消息 ──────────────────────────────────────────────────────


def test_get_messages_returns_empty_list(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """新会话没有消息时返回空列表（data 不是 null）。"""

    conversation_id = api_client.post(CONVERSATIONS, json={}, headers=auth_headers).json()["data"][
        "id"
    ]

    response = api_client.get(f"{CONVERSATIONS}/{conversation_id}/messages", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_messages_rejects_other_users_conversation(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """越权读取他人会话消息返回 404。"""

    conversation_id = api_client.post(CONVERSATIONS, json={}, headers=auth_headers).json()["data"][
        "id"
    ]
    other = _login_headers(api_client, "bob")

    response = api_client.get(f"{CONVERSATIONS}/{conversation_id}/messages", headers=other)

    assert response.status_code == 404
    assert response.json()["message"] == "会话不存在"


def test_get_messages_nonexistent_conversation(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """不存在的会话 ID 返回 404，而不是空列表。"""

    response = api_client.get(f"{CONVERSATIONS}/999999/messages", headers=auth_headers)

    assert response.status_code == 404


def test_messages_path_rejects_non_numeric_id(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """路径参数不是整数时返回 422，而不是 500。"""

    response = api_client.get(f"{CONVERSATIONS}/abc/messages", headers=auth_headers)

    assert response.status_code == 422


# ── 删除 ──────────────────────────────────────────────────────


def test_delete_conversation_returns_deleted_id(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """删除成功返回被删 ID，且列表随之为空。"""

    conversation_id = api_client.post(CONVERSATIONS, json={}, headers=auth_headers).json()["data"][
        "id"
    ]

    response = api_client.delete(f"{CONVERSATIONS}/{conversation_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == conversation_id
    assert api_client.get(CONVERSATIONS, headers=auth_headers).json()["data"]["total"] == 0


def test_delete_rejects_other_users_conversation(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """越权删除返回 404，且对方会话仍然存在。"""

    conversation_id = api_client.post(CONVERSATIONS, json={}, headers=auth_headers).json()["data"][
        "id"
    ]
    other = _login_headers(api_client, "bob")

    response = api_client.delete(f"{CONVERSATIONS}/{conversation_id}", headers=other)

    assert response.status_code == 404
    assert api_client.get(CONVERSATIONS, headers=auth_headers).json()["data"]["total"] == 1


# ── 鉴权 ──────────────────────────────────────────────────────


def test_conversations_require_auth(api_client: TestClient) -> None:
    """未带令牌一律 401。"""

    assert api_client.get(CONVERSATIONS).status_code == 401
    assert api_client.post(CONVERSATIONS, json={}).status_code == 401
    assert api_client.delete(f"{CONVERSATIONS}/1").status_code == 401
