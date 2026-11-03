"""会话服务测试（内存库，不需要数据库）。

重点是**跨用户隔离**：A 不能读写 B 的会话。这类越权一旦回归就是数据泄露，
因此每条隔离路径都要有反向用例。

断言只针对行为（异常消息），不绑定异常类型，便于后续替换异常体系。
"""

from __future__ import annotations

import pytest

from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.service.conversation_service import ConversationService
from tests.fakes import FakeMessageRepository, FakeSession, MemoryStore


@pytest.fixture()
def service(fake_repositories: MemoryStore, fake_session: FakeSession) -> ConversationService:
    """会话服务实例（Repository 已被换成内存实现）。"""

    return ConversationService(fake_session)


# ── 创建与列表 ────────────────────────────────────────────────


def test_create_conversation(service: ConversationService, alice: User) -> None:
    """创建会话并回传标题。"""

    out = service.create_conversation(alice, ConversationCreate(title="我的会话"))

    assert out.title == "我的会话"


def test_list_returns_only_own_conversations(
    service: ConversationService, alice: User, bob: User
) -> None:
    """用户只能看到自己的会话。"""

    service.create_conversation(alice, ConversationCreate(title="alice 的"))
    service.create_conversation(bob, ConversationCreate(title="bob 的"))

    result = service.list_conversations(alice, skip=0, limit=20)

    assert [item.title for item in result.items] == ["alice 的"]
    assert result.total == 1


def test_list_respects_pagination(service: ConversationService, alice: User) -> None:
    """分页参数生效。"""

    for index in range(3):
        service.create_conversation(alice, ConversationCreate(title=f"会话{index}"))

    page = service.list_conversations(alice, skip=0, limit=2)

    assert len(page.items) == 2
    assert page.total == 3


# ── 消息 ──────────────────────────────────────────────────────


def test_get_messages_returns_history(
    service: ConversationService,
    alice: User,
    alice_conversation: Conversation,
) -> None:
    """按时间正序返回历史消息。"""

    messages = FakeMessageRepository()
    messages.create(alice_conversation.id, "user", "较早的提问")
    messages.create(alice_conversation.id, "assistant", "较早的回答")

    history = service.get_messages(alice, alice_conversation.id)

    assert [m.content for m in history] == ["较早的提问", "较早的回答"]


def test_get_messages_returns_empty_for_new_conversation(
    service: ConversationService, alice: User, alice_conversation: Conversation
) -> None:
    """新会话没有消息时返回空列表，而不是报错。"""

    assert service.get_messages(alice, alice_conversation.id) == []


def test_get_messages_rejects_other_users_conversation(
    service: ConversationService, bob: User, alice_conversation: Conversation
) -> None:
    """越权读取他人会话消息必须被拒绝。"""

    with pytest.raises(Exception, match="会话不存在"):
        service.get_messages(bob, alice_conversation.id)


# ── 删除 ──────────────────────────────────────────────────────


def test_delete_own_conversation(
    service: ConversationService, alice: User, alice_conversation: Conversation
) -> None:
    """删除自己的会话成功。"""

    service.delete_conversation(alice, alice_conversation.id)

    assert service.list_conversations(alice, skip=0, limit=20).total == 0


def test_delete_cascades_messages(
    service: ConversationService,
    alice: User,
    alice_conversation: Conversation,
    store: MemoryStore,
) -> None:
    """删除会话时级联删除其消息，与外键 ondelete=CASCADE 行为一致。"""

    FakeMessageRepository().create(alice_conversation.id, "user", "提问")

    service.delete_conversation(alice, alice_conversation.id)

    assert store.messages == {}


def test_delete_rejects_other_users_conversation(
    service: ConversationService, bob: User, alice_conversation: Conversation
) -> None:
    """越权删除他人会话必须被拒绝，且不能真的删掉。"""

    with pytest.raises(Exception, match="会话不存在"):
        service.delete_conversation(bob, alice_conversation.id)

    assert service.list_conversations(bob, skip=0, limit=20).total == 0


def test_delete_nonexistent_conversation(service: ConversationService, alice: User) -> None:
    """删除不存在的会话给出明确报错，而不是静默成功。"""

    with pytest.raises(Exception, match="会话不存在"):
        service.delete_conversation(alice, 999999)
