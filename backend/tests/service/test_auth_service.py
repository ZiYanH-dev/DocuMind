"""认证服务测试（内存库，不需要数据库）。

断言方式说明：这里**只断言行为（异常消息），不断言异常类型**。
Service 层目前抛 HTTPException，后续若改为抛 AppError 子类，
这些用例不需要跟着改 —— 它们守住的是业务规则，而不是实现细节。
"""

from __future__ import annotations

import pytest

from app.core.security import decode_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import UserRegister
from app.service.auth_service import AuthService
from tests.fakes import FakeSession, FakeUserRepository, MemoryStore


@pytest.fixture()
def service(fake_repositories: MemoryStore, fake_session: FakeSession) -> AuthService:
    """认证服务实例（Repository 已被换成内存实现）。"""

    return AuthService(fake_session)


def _register_input(
    username: str, password: str = "123456", email: str | None = None
) -> UserRegister:
    """构造注册入参。"""

    return UserRegister(username=username, password=password, email=email)


# ── 注册 ──────────────────────────────────────────────────────


def test_register_creates_user(service: AuthService, store: MemoryStore) -> None:
    """注册成功并能在库中查到该用户。"""

    out = service.register(_register_input("alice"))

    assert out.username == "alice"
    assert FakeUserRepository().get_by_username("alice") is not None
    assert any(user.username == "alice" for user in store.users.values())


def test_register_hashes_password(service: AuthService, store: MemoryStore) -> None:
    """明文密码不得落库。"""

    service.register(_register_input("alice", password="plain-text"))

    user: User = next(user for user in store.users.values() if user.username == "alice")
    assert user.hashed_password != "plain-text"
    assert verify_password("plain-text", user.hashed_password) is True


def test_register_rejects_duplicate_username(service: AuthService) -> None:
    """用户名重复必须拒绝，否则会出现两个同名用户、登录时无法区分。"""

    service.register(_register_input("alice"))

    with pytest.raises(Exception, match="用户名已存在"):
        service.register(_register_input("alice"))


def test_register_rejects_duplicate_email(service: AuthService) -> None:
    """邮箱重复必须拒绝。"""

    service.register(_register_input("alice", email="a@example.com"))

    with pytest.raises(Exception, match="邮箱已被注册"):
        service.register(_register_input("bob", email="a@example.com"))


def test_register_allows_null_email_for_two_users(service: AuthService) -> None:
    """多个用户都不填邮箱时不应被判为重名（NULL 不等于 NULL）。"""

    service.register(_register_input("alice"))
    service.register(_register_input("bob"))

    assert service.login("bob", "123456").access_token


# ── 登录 ──────────────────────────────────────────────────────


def test_login_returns_usable_token(service: AuthService) -> None:
    """登录返回的令牌能解出正确的用户 ID。"""

    service.register(_register_input("alice"))
    token: str = service.login("alice", "123456").access_token

    user_id: str | None = decode_access_token(token)
    assert user_id is not None
    assert int(user_id) > 0


def test_login_rejects_wrong_password(service: AuthService) -> None:
    """密码错误必须拒绝。"""

    service.register(_register_input("alice", password="correct"))

    with pytest.raises(Exception, match="用户名或密码错误"):
        service.login("alice", "wrong")


def test_login_rejects_unknown_user(service: AuthService) -> None:
    """不存在的用户与密码错误返回同样的提示，避免暴露用户名是否存在。"""

    with pytest.raises(Exception, match="用户名或密码错误"):
        service.login("nobody", "123456")


def test_login_rejects_empty_password(service: AuthService) -> None:
    """空密码不能登录成功。"""

    service.register(_register_input("alice", password="123456"))

    with pytest.raises(Exception):
        service.login("alice", "")


# ── 当前用户 ──────────────────────────────────────────────────


def test_get_current_user_returns_profile(service: AuthService) -> None:
    """返回当前用户信息，且不含密码哈希。"""

    user: User = FakeUserRepository().create(
        username="alice", hashed_password=hash_password("123456")
    )

    out = service.get_current_user(user)

    assert out.username == "alice"
    assert not hasattr(out, "hashed_password")
