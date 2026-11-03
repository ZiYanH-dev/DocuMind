"""统一异常信封与中间件测试（不连数据库）。

这一层此前完全没被验证过，包括 ``AppError`` 的 handler ——
它注册了却没有任何业务代码抛出，等于死代码；至少要有用例证明它真的能工作，
以及各分支的状态码与业务码映射正确。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppError
from app.service.auth_service import AuthService

REGISTER = "/api/v1/auth/register"


def _raiser(exc: Exception) -> Callable[..., Any]:
    """返回一个"调用即抛指定异常"的可调用对象，用于替换服务方法。"""

    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise exc

    return _raise


# ── AppError（此前无任何业务代码抛出）─────────────────────────


def test_app_error_is_translated_to_envelope(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """抛出 AppError 时，业务码与 HTTP 状态码分别取自 code / status_code。"""

    monkeypatch.setattr(
        AuthService,
        "register",
        _raiser(AppError(code=1002, message="用户名已被占用", status_code=409)),
    )

    response = api_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 409
    assert response.json() == {
        "code": 1002,
        "message": "用户名已被占用",
        "data": None,
    }


def test_app_error_defaults_to_400(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """不传 status_code 时默认 400，业务码仍由 code 决定。"""

    monkeypatch.setattr(AuthService, "register", _raiser(AppError(code=1003, message="参数不合法")))

    response = api_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 400
    assert response.json()["code"] == 1003


# ── 数据库异常 ────────────────────────────────────────────────


def test_database_error_returns_500_with_business_code(
    lenient_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLAlchemyError 被翻译为 500 + 业务码 2001，而不是裸奔的堆栈。"""

    monkeypatch.setattr(
        AuthService, "register", _raiser(SQLAlchemyError("connection reset by peer"))
    )

    response = lenient_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == 2001
    assert "数据库操作异常" in body["message"]


def test_unexpected_error_returns_500_with_business_code(
    lenient_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未预期异常兜底为 500 + 业务码 9999，前端能统一处理。"""

    monkeypatch.setattr(AuthService, "register", _raiser(RuntimeError("boom")))

    response = lenient_client.post(REGISTER, json={"username": "alice", "password": "123456"})

    assert response.status_code == 500
    assert response.json()["code"] == 9999


# ── HTTPException 统一信封 ────────────────────────────────────


def test_unknown_route_uses_unified_envelope(api_client: TestClient) -> None:
    """不存在的路由也要返回信封，而不是 FastAPI 默认的 {"detail": ...}。"""

    response = api_client.get("/api/v1/not-exist")

    assert response.status_code == 404
    assert response.json() == {"code": 404, "message": "Not Found", "data": None}


def test_method_not_allowed_uses_unified_envelope(api_client: TestClient) -> None:
    """方法不匹配返回 405，且同样走信封。"""

    response = api_client.patch("/api/v1/auth/login", json={})

    assert response.status_code == 405
    assert response.json()["code"] == 405


def test_http_exception_keeps_www_authenticate_header(api_client: TestClient) -> None:
    """信封不能吃掉 WWW-Authenticate 头，浏览器/网关依赖它。"""

    response = api_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


# ── 健康检查与中间件 ──────────────────────────────────────────


def test_health_check(api_client: TestClient) -> None:
    """健康检查不鉴权、不进信封，供探针直接使用。"""

    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_duration_is_logged(
    api_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """中间件为每个请求打一条耗时日志，格式为 ``METHOD PATH -> CODE in Xms``。"""

    with caplog.at_level(logging.INFO, logger="app"):
        api_client.get("/health")

    assert "GET /health -> 200 in" in caplog.text


def test_cors_headers_present_for_allowed_origin(api_client: TestClient) -> None:
    """跨域请求带上 CORS 头，前端才能直连后端。"""

    response = api_client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert "access-control-allow-origin" in {key.lower() for key in response.headers}
