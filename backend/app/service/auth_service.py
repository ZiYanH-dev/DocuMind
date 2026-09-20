"""认证服务：注册、登录、当前用户。"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repository.user_repository import UserRepository
from app.schemas.auth import TokenOut, UserOut, UserRegister


class AuthService:
    """认证业务逻辑。"""

    def __init__(self, db: Session) -> None:
        self._repository: UserRepository = UserRepository(db)

    def register(self, user_in: UserRegister) -> UserOut:
        """用户注册。"""

        if self._repository.get_by_username(user_in.username) is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )
        if user_in.email is not None and self._repository.get_by_email(user_in.email) is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被注册",
            )

        hashed: str = hash_password(user_in.password)
        user: User = self._repository.create(
            username=user_in.username,
            hashed_password=hashed,
            email=user_in.email,
        )
        logger.info("user registered: %s", user.username)
        return UserOut.model_validate(user)

    def login(self, username: str, password: str) -> TokenOut:
        """用户登录，返回 JWT 令牌。"""

        user: User | None = self._repository.get_by_username(username)
        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        token: str = create_access_token(subject=str(user.id))
        logger.info("user logged in: %s", username)
        return TokenOut(access_token=token)

    def get_current_user(self, user: User) -> UserOut:
        """获取当前用户信息。"""

        return UserOut.model_validate(user)
