"""认证相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """用户注册请求。"""

    username: str = Field(min_length=3, max_length=50, description="用户名")
    email: EmailStr | None = Field(default=None, description="邮箱")
    password: str = Field(min_length=6, max_length=128, description="密码")


class UserLogin(BaseModel):
    """用户登录请求。"""

    username: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="密码")


class UserOut(BaseModel):
    """用户信息响应。"""

    id: int
    username: str
    email: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    """登录令牌响应。"""

    access_token: str
    token_type: str = "bearer"
