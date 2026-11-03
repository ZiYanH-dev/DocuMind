"""HTTP 层测试夹具：TestClient + 内存替身，全程不连数据库与 Redis。

为什么需要这一层
----------------
此前所有 HTTP 行为（状态码、统一响应信封、鉴权失败、参数校验、SSE 帧格式）
都只能靠 ``tests/integration`` 验证，而集成测试需要真实 PostgreSQL，
在没起 Docker 的机器上全部跳过 —— 等于这块长期无人看守。

覆盖 ``get_db`` 依赖后，路由与鉴权依赖都拿到内存替身，
HTTP 层的行为就可以独立验证；集成层只保留"真 SQL 才有的语义"。
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.agent.agent import ChatAgentBundle
from app.config.database import get_db
from app.main import app
from app.service import chat_service as chat_service_module
from tests.fakes import FakeCache, FakeSession, MemoryStore, RecordingGraph


def _build_client(
    fake_session: FakeSession, *, raise_server_exceptions: bool
) -> Generator[TestClient, None, None]:
    """构造 TestClient：用内存 Session 覆盖 ``get_db``，不触碰真实数据库。

    ``raise_server_exceptions=False`` 用于观察**真实生产响应** ——
    默认的 True 会把未捕获异常重新抛出，看不到兜底 handler 实际返回了什么。
    """

    def _override_get_db() -> Generator[FakeSession, None, None]:
        yield fake_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=raise_server_exceptions) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def api_client(
    fake_repositories: MemoryStore,
    fake_cache: FakeCache,
    fake_session: FakeSession,
) -> Generator[TestClient, None, None]:
    """普通 TestClient：服务端异常会重新抛出，便于暴露 bug。"""

    yield from _build_client(fake_session, raise_server_exceptions=True)


@pytest.fixture()
def lenient_client(
    fake_repositories: MemoryStore,
    fake_cache: FakeCache,
    fake_session: FakeSession,
) -> Generator[TestClient, None, None]:
    """不重抛服务端异常的客户端，返回的是线上真实响应体。"""

    yield from _build_client(fake_session, raise_server_exceptions=False)


@pytest.fixture()
def auth_headers(api_client: TestClient) -> dict[str, str]:
    """注册并登录，返回带 Bearer token 的请求头。"""

    api_client.post("/api/v1/auth/register", json={"username": "tester", "password": "123456"})
    response = api_client.post(
        "/api/v1/auth/login", json={"username": "tester", "password": "123456"}
    )
    assert response.status_code == 200, response.text
    token: str = str(response.json()["data"]["access_token"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def graph(monkeypatch: pytest.MonkeyPatch, api_client: TestClient) -> RecordingGraph:
    """替换 Agent 工厂为假图，让 SSE 接口可以离线验证。

    依赖 ``api_client`` 是为了保证覆盖在请求发生前就已生效；``monkeypatch``
    在用例结束后自动还原。
    """

    recorder: RecordingGraph = RecordingGraph()
    bundle = ChatAgentBundle(agent=cast(Any, recorder), retrieved_hits=recorder.hits)
    monkeypatch.setattr(chat_service_module, "create_chat_agent", lambda session, user_id: bundle)
    return recorder
