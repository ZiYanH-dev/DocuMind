"""会话 API 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    MessageOut,
)
from app.schemas.response import ApiResponse, DeleteOut
from app.service.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["会话"])


@router.post("", response_model=ApiResponse[ConversationOut])
def create_conversation(
    conversation_in: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ConversationOut]:
    """创建会话。"""

    service: ConversationService = ConversationService(db)
    return ApiResponse(data=service.create_conversation(current_user, conversation_in))


@router.get("", response_model=ApiResponse[ConversationListOut])
def list_conversations(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ConversationListOut]:
    """获取会话列表。"""

    service: ConversationService = ConversationService(db)
    return ApiResponse(data=service.list_conversations(current_user, skip, limit))


@router.get("/{conversation_id}/messages", response_model=ApiResponse[list[MessageOut]])
def get_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[list[MessageOut]]:
    """获取会话的消息历史。"""

    service: ConversationService = ConversationService(db)
    return ApiResponse(data=service.get_messages(current_user, conversation_id))


@router.delete("/{conversation_id}", response_model=ApiResponse[DeleteOut], status_code=200)
def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DeleteOut]:
    """删除会话。"""

    service: ConversationService = ConversationService(db)
    service.delete_conversation(current_user, conversation_id)
    return ApiResponse(data=DeleteOut(id=conversation_id))
