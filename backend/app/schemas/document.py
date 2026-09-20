"""文档相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    """文档信息响应。"""

    id: int
    title: str
    file_name: str
    file_size: int
    file_type: str
    status: str
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    """文档列表响应。"""

    total: int
    items: list[DocumentOut]
