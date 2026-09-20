"""问答聊天相关 Schema。"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """发送消息请求。"""

    conversation_id: int | None = Field(default=None, description="会话 ID，为空则创建新会话")
    content: str = Field(min_length=1, max_length=8000, description="用户消息内容")


class SourceInfo(BaseModel):
    """回答引用来源。"""

    document_id: int
    document_title: str
    chunk_index: int
    snippet: str
    score: float
