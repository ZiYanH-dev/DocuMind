"""认证 API 的 HTTP 行为测试（不连数据库）。

这一层守的是**协议契约**：状态码、统一响应信封、鉴权失败的头信息。
业务规则（重名、密码校验）已由 service 层覆盖，这里不重复测。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def _register(client: TestClient, username: str = "alice", password: str = "123456") -> dict:
    """注册并返回响应 JSON。"""

    return client.post(REGISTER, json={"username": username, "password": password}).json()


# ── 注册 ──────────────────────────────────────────────────────


def test_register_returns_unified_envelope(api_client: TestClient) -> None:
    """成功响应必须是 {code:0, message, data} 信封，前端统一解析。"""

    response = api_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert body["data"]["username"] == "alice"


def test_register_never_leaks_password(api_client: TestClient) -> None:
    """响应体不得包含任何密码字段，包括哈希。"""

    response = api_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert "password" not in response.text
    assert "hashed" not in response.text


def test_duplicate_username_returns_400_with_message(api_client: TestClient) -> None:
    """重名返回 400，且 message 带上真实原因（前端直接展示）。"""

    _register(api_client)
    response = api_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 400
    assert response.json() == {"code": 400, "message": "用户名已存在", "data": None}


def test_invalid_payload_returns_422_with_field_errors(api_client: TestClient) -> None:
    """参数校验失败返回 422，并把出错字段回传，便于前端定位。"""

    response = api_client.post(REGISTER, json={"username": "alice", "password": "1"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 1001
    assert body["message"] == "请求参数校验失败"
    assert any("password" in item["field"] for item in body["data"])


def test_missing_field_returns_422(api_client: TestClient) -> None:
    """缺少必填字段同样是 422，而不是 500。"""

    response = api_client.post(REGISTER, json={"username": "alice"})

    assert response.status_code == 422
    assert response.json()["code"] == 1001


# ── 登录 ──────────────────────────────────────────────────────


def test_login_returns_token(api_client: TestClient) -> None:
    """登录返回可用的 access_token。"""

    _register(api_client)

    response = api_client.post(LOGIN, json={"username": "alice", "password": "123456"})

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]


def test_login_wrong_password_returns_401(api_client: TestClient) -> None:
    """密码错误返回 401，并给出可读提示。"""

    _register(api_client)

    response = api_client.post(LOGIN, json={"username": "alice", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["message"] == "用户名或密码错误"


# ── 鉴权 ──────────────────────────────────────────────────────


def test_me_requires_token(api_client: TestClient) -> None:
    """未带令牌返回 401，并附带标准 WWW-Authenticate 头。"""

    response = api_client.get(ME)

    assert response.status_code == 401
    assert response.json()["message"] == "未提供认证令牌"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_invalid_token(api_client: TestClient) -> None:
    """伪造的令牌被拒绝，且不泄露内部细节。"""

    response = api_client.get(ME, headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["message"] == "令牌无效或已过期"


def test_me_rejects_token_of_deleted_user(api_client: TestClient) -> None:
    """令牌合法但用户已不存在时返回 401，而不是 500。"""

    token: str = create_access_token(subject="99999")

    response = api_client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["message"] == "用户不存在"


def test_me_returns_current_user(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    """带合法令牌返回当前用户信息。"""

    response = api_client.get(ME, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["username"] == "tester"


@pytest.mark.xfail(
    strict=True,
    reason="已知缺陷：deps.py 直接 int(user_id_str)，非数字 subject 抛 ValueError",
)
def test_me_tolerates_non_numeric_subject(lenient_client: TestClient) -> None:
    """令牌 subject 非数字时应返回 401（无效令牌），而不是 500。

    现状（实测）：``app/core/deps.py:37`` 直接 ``int(user_id_str)``，
    ValueError 冒泡到兜底 handler，返回 500 且把异常字符串回显给客户端。
    非数字 subject 的令牌无法由外部伪造（需要签名密钥），所以不构成直接
    可利用的漏洞；但"一段畸形令牌把接口打成 500 并泄露内部信息"仍是缺陷。
    修法：把 int() 包进 try/except，或改用不会抛的解析函数。
    """

    token: str = create_access_token(subject="not-a-number")

    response = lenient_client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
