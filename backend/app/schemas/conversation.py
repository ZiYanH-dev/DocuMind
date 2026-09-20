"""会话相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """创建会话请求。"""

    title: str = Field(default="新对话", max_length=255, description="会话标题")


class ConversationOut(BaseModel):
    """会话信息响应。"""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListOut(BaseModel):
    """会话列表响应。"""

    total: int
    items: list[ConversationOut]


class MessageOut(BaseModel):
    """消息响应。"""

    id: int
    role: str
    content: str
    sources: list | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
