"""认证 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.auth import TokenOut, UserLogin, UserOut, UserRegister
from app.schemas.response import ApiResponse
from app.service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ApiResponse[UserOut])
def register(user_in: UserRegister, db: Session = Depends(get_db)) -> ApiResponse[UserOut]:
    """用户注册。"""

    service: AuthService = AuthService(db)
    return ApiResponse(data=service.register(user_in))


@router.post("/login", response_model=ApiResponse[TokenOut])
def login(user_in: UserLogin, db: Session = Depends(get_db)) -> ApiResponse[TokenOut]:
    """用户登录。"""

    service: AuthService = AuthService(db)
    return ApiResponse(data=service.login(user_in.username, user_in.password))


@router.get("/me", response_model=ApiResponse[UserOut])
def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserOut]:
    """获取当前用户信息。"""

    return ApiResponse(data=UserOut.model_validate(current_user))
