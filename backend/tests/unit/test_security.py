"""鉴权与密码安全单元测试。

这些是安全边界，一旦回归就是越权漏洞，因此必须覆盖反向用例
（错误密码、过期令牌、篡改签名、他人密钥签发的令牌）。
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta

from jose import jwt

from app.config.settings import settings
from app.core.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ── 密码哈希 ──────────────────────────────────────────────────


def test_hash_is_not_plaintext() -> None:
    """入库的必须是哈希，绝不能是明文。"""

    hashed: str = hash_password("123456")

    assert hashed != "123456"
    assert hashed


def test_verify_accepts_correct_password() -> None:
    """正确密码校验通过。"""

    assert verify_password("123456", hash_password("123456")) is True


def test_verify_rejects_wrong_password() -> None:
    """错误密码校验失败。"""

    assert verify_password("wrong", hash_password("123456")) is False


def test_same_password_produces_different_hashes() -> None:
    """bcrypt 自带随机盐，相同明文两次哈希结果不同，防止彩虹表比对。"""

    assert hash_password("123456") != hash_password("123456")


# ── JWT ──────────────────────────────────────────────────────


def test_token_roundtrip() -> None:
    """签发的令牌能解回原 subject。"""

    token: str = create_access_token(subject="42")

    assert decode_access_token(token) == "42"


def test_token_uses_custom_expiry() -> None:
    """可传入自定义有效期。"""

    token: str = create_access_token(subject="42", expires_delta=timedelta(minutes=1))

    assert decode_access_token(token) == "42"


def test_expired_token_is_rejected() -> None:
    """过期令牌必须解不出来，否则等于永久有效。"""

    token: str = create_access_token(subject="42", expires_delta=timedelta(seconds=-1))

    assert decode_access_token(token) is None


def test_tampered_signature_is_rejected() -> None:
    """篡改签名的令牌必须被拒绝。"""

    token: str = create_access_token(subject="42")
    header, payload, signature = token.split(".")

    assert decode_access_token(f"{header}.{payload}.{signature[:-4]}abcd") is None


def test_token_signed_by_other_secret_is_rejected() -> None:
    """用别的密钥签发的令牌不能通过校验（防伪造）。"""

    foreign_token: str = jwt.encode(
        {"sub": "42", "exp": 9999999999}, "another-secret", algorithm=ALGORITHM
    )

    assert decode_access_token(foreign_token) is None


def test_malformed_token_is_rejected() -> None:
    """非 JWT 字符串不应抛异常，而是安全返回 None。"""

    assert decode_access_token("not-a-jwt") is None
    assert decode_access_token("") is None


def test_token_without_subject_returns_none() -> None:
    """缺少 sub 声明的令牌返回 None，而不是抛出或返回 "None" 字符串。"""

    token: str = jwt.encode({"exp": 9999999999}, settings.secret_key, algorithm=ALGORITHM)

    assert decode_access_token(token) is None


def test_token_signed_with_other_algorithm_is_rejected() -> None:
    """用 HS512 签发的令牌必须被拒绝，解码端只认 HS256。"""

    token: str = jwt.encode(
        {"sub": "42", "exp": 9999999999}, settings.secret_key, algorithm="HS512"
    )

    assert decode_access_token(token) is None


def test_alg_none_token_is_rejected() -> None:
    """alg=none 的令牌（无签名）必须被拒绝，防止伪造身份。

    python-jose 不允许直接用 alg=none 签发，因此这里手工拼一个：
    头部声明 alg=none、签名为空串。
    """

    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header: str = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload: str = _b64(json.dumps({"sub": "42", "exp": 9999999999}).encode())
    forged: str = f"{header}.{payload}."

    assert decode_access_token(forged) is None
