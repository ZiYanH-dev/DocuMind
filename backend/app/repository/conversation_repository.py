"""会话仓库。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


class ConversationRepository:
    """会话表数据访问。"""

    def __init__(self, db: Session) -> None:
        self._db: Session = db

    def create(self, user_id: int, title: str) -> Conversation:
        """创建会话。"""

        conversation = Conversation(user_id=user_id, title=title)
        self._db.add(conversation)
        self._db.commit()
        self._db.refresh(conversation)
        return conversation

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        """按 ID 查询会话。"""

        return self._db.get(Conversation, conversation_id)

    def get_by_user_id(self, user_id: int, conversation_id: int) -> Conversation | None:
        """按用户 ID + 会话 ID 查询（校验归属）。"""

        return (
            self._db.query(Conversation)
            .filter(Conversation.user_id == user_id, Conversation.id == conversation_id)
            .first()
        )

    def list_by_user_id(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Conversation]:
        """查询用户会话列表（分页）。"""

        return (
            self._db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user_id(self, user_id: int) -> int:
        """统计用户会话数量。"""

        return (
            self._db.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == user_id)
            )
            or 0
        )

    def update_title(self, conversation_id: int, title: str) -> None:
        """更新会话标题。"""

        conversation = self._db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.title = title
            self._db.commit()

    def delete(self, conversation: Conversation) -> None:
        """删除会话（级联删除消息）。"""

        self._db.delete(conversation)
        self._db.commit()


class MessageRepository:
    """消息表数据访问。"""

    def __init__(self, db: Session) -> None:
        self._db: Session = db

    def create(
        self,
        conversation_id: int,
        role: str,
        content: str,
        sources: list | None = None,
    ) -> Message:
        """创建消息。"""

        message = Message(
            conversation_id=conversation_id, role=role, content=content, sources=sources
        )

        self._db.add(message)
        self._db.commit()
        self._db.refresh(message)
        return message

    def list_by_conversation_id(self, conversation_id: int) -> list[Message]:
        """查询会话的全部消息（按时间正序）。"""

        return (
            self._db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .all()
        )
