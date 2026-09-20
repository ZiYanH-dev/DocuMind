"""安全模块：JWT 令牌与密码哈希。"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM: str = "HS256"


def hash_password(password: str) -> str:
    """对明文密码进行哈希。"""

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配。"""

    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    """创建 JWT 访问令牌。"""

    expire: datetime = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode: dict[str, object] = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """解码 JWT 令牌，返回 subject（用户ID）。"""

    try:
        payload: dict[str, object] = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject: object = payload.get("sub")

        return str(subject) if subject is not None else None
    except JWTError:
        return None
