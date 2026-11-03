"""服务层测试用的内存 Repository 替身。

为什么需要它
------------
服务层的业务规则（用户名去重、跨用户越权、文档状态流转、文件名安全）
本质上与数据库无关。让这些用例依赖真实 PostgreSQL 会带来两个代价：
一是没有 Docker 就跑不了，二是 20 多毫秒的用例被拖到秒级。

标准做法是在**数据访问边界**做替身：内存实现与真实 Repository 同名同签名，
通过 monkeypatch 换掉类即可，服务代码一行不用改。

这些替身**只实现服务层真正调用到的方法**。SQL 正确性（pgvector 余弦检索、
级联删除、迁移脚本）不在这里验证，那部分由 tests/integration/ 用真实数据库覆盖。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.schemas.chat import SourceInfo


class FakeSession:
    """Session 替身：只保留服务层合理使用的提交语义。

    服务层不该绕过 Repository 直接查库。这里刻意不实现 ``query`` / ``execute``
    / ``get``，一旦越界就抛 ``AttributeError`` —— 比 Mock 静默返回更容易发现，
    也避免"测试通过、实际却走了另一条路径"。
    """

    def __init__(self) -> None:
        self.commit_count: int = 0
        self.refresh_count: int = 0

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, instance: object) -> None:
        self.refresh_count += 1

    def rollback(self) -> None:
        return None


class FakeCache:
    """RedisCache 的内存替身，记录写入以便断言缓存行为。

    真实 ``cache`` 在 Redis 不可用时静默降级，若直接断言"有没有写缓存"
    会变成假通过；换成这个替身之后，缓存行为可被确定性验证。
    """

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.set_calls: list[tuple[str, Any, int]] = []
        self.deleted_prefixes: list[str] = []

    def get_json(self, key: str) -> Any | None:
        return self.data.get(key)

    def set_json(self, key: str, value: Any, ttl: int = 0) -> None:
        self.data[key] = value
        self.set_calls.append((key, value, ttl))

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.data.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        self.deleted_prefixes.append(prefix)
        for key in list(self.data):
            if key.startswith(prefix):
                del self.data[key]


# 固定起始时间：让 created_at 可预测，且不依赖真实时钟
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class MemoryStore:
    """内存数据表集合，模拟一个数据库实例。"""

    users: dict[int, User] = field(default_factory=dict)
    documents: dict[int, Document] = field(default_factory=dict)
    chunks: dict[int, DocumentChunk] = field(default_factory=dict)
    conversations: dict[int, Conversation] = field(default_factory=dict)
    messages: dict[int, Message] = field(default_factory=dict)
    _seq: int = 0
    _tick: int = 0

    def next_id(self) -> int:
        """自增主键，等价数据库的 autoincrement。"""

        self._seq += 1
        return self._seq

    def now(self) -> datetime:
        """单调递增的时间，保证排序语义与真实库一致。"""

        self._tick += 1
        return _EPOCH + timedelta(seconds=self._tick)


_STORE: MemoryStore = MemoryStore()


def get_store() -> MemoryStore:
    """获取当前测试使用的内存库。"""

    return _STORE


def reset_store() -> MemoryStore:
    """清空内存库，保证用例之间互不污染。"""

    global _STORE
    _STORE = MemoryStore()
    return _STORE


# ── 用户 ──────────────────────────────────────────────────────


class FakeUserRepository:
    """UserRepository 的内存实现。"""

    def __init__(self, db: object = None) -> None:
        self._store: MemoryStore = get_store()

    def get_by_id(self, user_id: int) -> User | None:
        return self._store.users.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return next(
            (user for user in self._store.users.values() if user.username == username), None
        )

    def get_by_email(self, email: str) -> User | None:
        # 真实实现里 email 可为 NULL，传 None 时不应命中任何记录
        if email is None:
            return None
        return next((user for user in self._store.users.values() if user.email == email), None)

    def create(self, username: str, hashed_password: str, email: str | None = None) -> User:
        moment: datetime = self._store.now()
        user: User = User(
            id=self._store.next_id(),
            username=username,
            hashed_password=hashed_password,
            email=email,
            is_active=True,
            created_at=moment,
            updated_at=moment,
        )
        self._store.users[user.id] = user
        return user


# ── 会话 ──────────────────────────────────────────────────────


class FakeConversationRepository:
    """ConversationRepository 的内存实现。"""

    def __init__(self, db: object = None) -> None:
        self._store: MemoryStore = get_store()

    def create(self, user_id: int, title: str) -> Conversation:
        moment: datetime = self._store.now()
        conversation: Conversation = Conversation(
            id=self._store.next_id(),
            user_id=user_id,
            title=title,
            created_at=moment,
            updated_at=moment,
        )
        self._store.conversations[conversation.id] = conversation
        return conversation

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        return self._store.conversations.get(conversation_id)

    def get_by_user_id(self, user_id: int, conversation_id: int) -> Conversation | None:
        conversation: Conversation | None = self._store.conversations.get(conversation_id)
        # 归属校验：会话存在但不属于该用户时，必须当作不存在
        if conversation is None or conversation.user_id != user_id:
            return None
        return conversation

    def list_by_user_id(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Conversation]:
        owned: list[Conversation] = [
            conversation
            for conversation in self._store.conversations.values()
            if conversation.user_id == user_id
        ]
        owned.sort(key=lambda item: item.updated_at, reverse=True)
        return owned[skip : skip + limit]

    def count_by_user_id(self, user_id: int) -> int:
        return sum(
            1
            for conversation in self._store.conversations.values()
            if conversation.user_id == user_id
        )

    def update_title(self, conversation_id: int, title: str) -> None:
        conversation: Conversation | None = self._store.conversations.get(conversation_id)
        if conversation is not None:
            conversation.title = title

    def delete(self, conversation: Conversation) -> None:
        # 级联删除消息，与外键 ondelete="CASCADE" 行为一致
        for message_id, message in list(self._store.messages.items()):
            if message.conversation_id == conversation.id:
                del self._store.messages[message_id]
        self._store.conversations.pop(conversation.id, None)


class FakeMessageRepository:
    """MessageRepository 的内存实现。"""

    def __init__(self, db: object = None) -> None:
        self._store: MemoryStore = get_store()

    def create(
        self,
        conversation_id: int,
        role: str,
        content: str,
        sources: list | None = None,
    ) -> Message:
        message: Message = Message(
            id=self._store.next_id(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
            created_at=self._store.now(),
        )
        self._store.messages[message.id] = message
        return message

    def list_by_conversation_id(self, conversation_id: int) -> list[Message]:
        messages: list[Message] = [
            message
            for message in self._store.messages.values()
            if message.conversation_id == conversation_id
        ]
        messages.sort(key=lambda item: item.created_at)
        return messages


# ── 文档 ──────────────────────────────────────────────────────


class FakeDocumentRepository:
    """DocumentRepository 的内存实现。"""

    def __init__(self, db: object = None) -> None:
        self._store: MemoryStore = get_store()

    def create(
        self,
        user_id: int,
        title: str,
        file_name: str,
        file_path: str,
        file_size: int,
        file_type: str,
    ) -> Document:
        moment: datetime = self._store.now()
        document: Document = Document(
            id=self._store.next_id(),
            user_id=user_id,
            title=title,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            status="processing",
            created_at=moment,
            updated_at=moment,
        )
        self._store.documents[document.id] = document
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        return self._store.documents.get(document_id)

    def get_by_user_id(self, user_id: int, document_id: int) -> Document | None:
        document: Document | None = self._store.documents.get(document_id)
        if document is None or document.user_id != user_id:
            return None
        return document

    def list_by_user_id(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Document]:
        owned: list[Document] = [
            document for document in self._store.documents.values() if document.user_id == user_id
        ]
        owned.sort(key=lambda item: item.created_at, reverse=True)
        return owned[skip : skip + limit]

    def count_by_user_id(self, user_id: int) -> int:
        return sum(1 for document in self._store.documents.values() if document.user_id == user_id)

    def count_chunks(self, document_id: int) -> int:
        return sum(1 for chunk in self._store.chunks.values() if chunk.document_id == document_id)

    def update_status(
        self, document_id: int, status: str, error_message: str | None = None
    ) -> None:
        document: Document | None = self._store.documents.get(document_id)
        if document is not None:
            document.status = status
            document.error_message = error_message

    def delete(self, document: Document) -> None:
        for chunk_id, chunk in list(self._store.chunks.items()):
            if chunk.document_id == document.id:
                del self._store.chunks[chunk_id]
        self._store.documents.pop(document.id, None)

    def delete_chunks_by_document_id(self, document_id: int) -> None:
        for chunk_id, chunk in list(self._store.chunks.items()):
            if chunk.document_id == document_id:
                del self._store.chunks[chunk_id]


class FakeChunkRepository:
    """ChunkRepository 的内存实现。

    只实现服务层用到的写入与语料读取方法；``vector_search`` 依赖 pgvector 的
    ``<->`` 算子，无法在内存里等价复现，这里显式报错——它属于集成测试的领地。
    """

    def __init__(self, db: object = None) -> None:
        self._store: MemoryStore = get_store()

    def create_many(self, chunks: list[DocumentChunk]) -> None:
        for chunk in chunks:
            chunk.id = self._store.next_id()
            chunk.created_at = self._store.now()
            self._store.chunks[chunk.id] = chunk

    def list_all_by_user(self, user_id: int) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for chunk in self._store.chunks.values():
            document: Document | None = self._store.documents.get(chunk.document_id)
            if document is None or document.user_id != user_id:
                continue
            rows.append(
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "document_title": document.title,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                }
            )
        rows.sort(key=lambda row: int(row["chunk_id"]))  # type: ignore[arg-type]
        return rows

    def corpus_fingerprint(self, user_id: int) -> str:
        chunk_ids: list[int] = [
            chunk.id
            for chunk in self._store.chunks.values()
            if (document := self._store.documents.get(chunk.document_id)) is not None
            and document.user_id == user_id
        ]
        if not chunk_ids:
            return "empty"
        return f"{len(chunk_ids)}:{min(chunk_ids)}:{max(chunk_ids)}"

    def vector_search(
        self,
        user_id: int,
        embedding: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, object]]:
        raise NotImplementedError(
            "向量检索依赖 pgvector 的余弦算子，应在 tests/integration/ 用真实数据库验证"
        )


# ── 假 Agent 图（chat_service 与服务层/HTTP 层测试共用）─────────


@dataclass
class RecordingGraph:
    """假 Agent 图：记录入参并按脚本回放事件，完全不调用真实 LLM。

    与 ``CompiledStateGraph.stream`` 同名同签名。``events`` 里放的是 LangGraph
    真实的 ``(stream_mode, event)`` 事件对，因此被测代码走的抽取/过滤分支
    与线上一致。
    """

    events: list[tuple[str, Any]] = field(default_factory=list)
    hits: list[SourceInfo] = field(default_factory=list)
    payloads: list[dict[str, Any]] = field(default_factory=list)
    stream_modes: list[Any] = field(default_factory=list)

    def stream(self, payload: dict[str, Any], stream_mode: Any = None) -> Iterator[tuple[str, Any]]:
        """回放预置事件，并记录入参与 stream_mode 供断言。"""

        self.payloads.append(payload)
        self.stream_modes.append(stream_mode)
        yield from self.events


def token_event(text: str, node: str = "model") -> tuple[str, Any]:
    """构造主回答节点产出的 messages 事件。"""

    return ("messages", (AIMessageChunk(content=text), {"langgraph_node": node}))


def tool_update_event(*names: str) -> tuple[str, Any]:
    """构造 tools 节点执行工具后的 updates 事件。"""

    messages: list[ToolMessage] = [
        ToolMessage(content="命中 3 段", name=name, tool_call_id=f"call-{index}")
        for index, name in enumerate(names)
    ]
    return ("updates", {"tools": {"messages": messages}})


def make_source(document_id: int, chunk_index: int, title: str = "rag.txt") -> SourceInfo:
    """构造一条检索命中。"""

    return SourceInfo(
        document_id=document_id,
        document_title=title,
        chunk_index=chunk_index,
        snippet="片段内容",
        score=0.9,
    )
