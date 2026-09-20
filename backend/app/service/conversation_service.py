"""会话服务：会话 CRUD 与消息历史。"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.conversation import Conversation
from app.models.user import User
from app.repository.conversation_repository import ConversationRepository, MessageRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListOut,
    ConversationOut,
    MessageOut,
)


class ConversationService:
    """会话业务逻辑。"""

    def __init__(self, db: Session) -> None:
        self._repository: ConversationRepository = ConversationRepository(db)
        self._message_repository: MessageRepository = MessageRepository(db)

    def create_conversation(self, user: User, conversation_in: ConversationCreate) -> ConversationOut:
        """创建会话。"""

        conversation: Conversation = self._repository.create(user.id, conversation_in.title)
        logger.info(
            "conversation created, user_id=%s conv_id=%s", user.id, conversation.id
        )
        return ConversationOut.model_validate(conversation)

    def list_conversations(self, user: User, skip: int, limit: int) -> ConversationListOut:
        """查询用户会话列表。"""

        conversations: list[Conversation] = self._repository.list_by_user_id(user.id, skip, limit)
        total: int = self._repository.count_by_user_id(user.id)
        return ConversationListOut(
            total=total,
            items=[ConversationOut.model_validate(conv) for conv in conversations],
        )

    def delete_conversation(self, user: User, conversation_id: int) -> None:
        """删除会话。"""

        conversation: Conversation | None = self._repository.get_by_user_id(user.id, conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        self._repository.delete(conversation)
        logger.info(
            "conversation deleted, user_id=%s conv_id=%s", user.id, conversation_id
        )

    def get_messages(self, user: User, conversation_id: int) -> list[MessageOut]:
        """查询会话消息历史。"""

        conversation: Conversation | None = self._repository.get_by_user_id(user.id, conversation_id)
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        messages = self._message_repository.list_by_conversation_id(conversation_id)
        return [MessageOut.model_validate(msg) for msg in messages]
