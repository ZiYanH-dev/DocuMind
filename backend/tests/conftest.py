"""pytest 全局夹具：环境变量引导 + 数据库 / HTTP 夹具。

三条设计约定：

1. **环境变量必须先于 ``app.*`` 导入设置**。``Settings`` 在模块导入时就完成实例化
   并被 ``lru_cache`` 缓存，导入之后再改环境变量无效。
2. **只设 Settings 真实存在的键**。它用分字段（``POSTGRES_HOST/PORT/USER/
   PASSWORD/DB``、``REDIS_HOST/PORT/DB``）推导连接串，且 ``extra="ignore"``，
   因此旧的 ``DATABASE_URL`` / ``REDIS_URL`` 会被静默丢弃 —— 那是失效配置。
3. **数据库不可用时 skip 而不是 error**。这样在没有 Docker 的机器上，
   纯逻辑的单元测试依然能全量运行，只有真正需要库的用例被跳过。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace

# ── 环境变量引导（必须在导入 app.* 之前）─────────────────────────

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "false")  # 关掉 SQL echo，避免日志被 SQL 刷屏
os.environ.setdefault("POSTGRES_DB", "documind_test")  # 指向测试库，绝不碰开发库
os.environ.setdefault("REDIS_DB", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("EMBEDDING_MODEL", "test-embedding")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config.database import Base, get_db  # noqa: E402
from app.config.embedding_client import EmbeddingService  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.user import User  # noqa: E402
from tests.fakes import (  # noqa: E402
    FakeCache,
    FakeChunkRepository,
    FakeConversationRepository,
    FakeDocumentRepository,
    FakeMessageRepository,
    FakeSession,
    FakeUserRepository,
    MemoryStore,
    get_store,
    reset_store,
)

TEST_DATABASE_URL: str = settings.resolved_database_url
ENGINE = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


# ── 全局替身 ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """离线替掉真实 Embedding 调用，避免测试依赖网络与密钥。

    维度取 ``settings.embedding_dim``，与 ``document_chunks.embedding`` 列保持
    一致，避免迁移调整维度后这里写死的旧值导致入库失败。
    """

    def _fake_embed_texts(self, texts, *args, **kwargs):
        return [[0.0] * settings.embedding_dim for _ in texts]

    def _fake_embed_query(self, text, *args, **kwargs):
        return [0.0] * settings.embedding_dim

    monkeypatch.setattr(EmbeddingService, "embed_texts", _fake_embed_texts)
    monkeypatch.setattr(EmbeddingService, "embed_query", _fake_embed_query)


# ── 数据库夹具 ────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _prepare_db() -> Generator[None, None, None]:
    """建表并在结束后清表；数据库不可用时整批 skip。"""

    try:
        with ENGINE.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"测试数据库不可用（{TEST_DATABASE_URL}）：{exc}。"
            f"请先执行 make db-init 启动 PostgreSQL 并创建库 documind_test",
            allow_module_level=False,
        )
        return

    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)
    yield
    Base.metadata.drop_all(ENGINE)


@pytest.fixture()
def db_session(_prepare_db: None) -> Generator[Session, None, None]:
    """每个用例一个独立事务，结束后回滚，用例之间互不污染。"""

    connection = ENGINE.connect()
    transaction = connection.begin()
    session: Session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient，覆盖 get_db 依赖以复用测试事务。"""

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── 内存库夹具（服务层测试用，不需要数据库）────────────────────


@pytest.fixture(autouse=True)
def _reset_fake_store() -> Generator[MemoryStore, None, None]:
    """每个用例前后清空内存库，保证用例之间互不污染。"""

    store: MemoryStore = reset_store()
    yield store
    reset_store()


@pytest.fixture()
def store(_reset_fake_store: MemoryStore) -> MemoryStore:
    """当前用例的内存库句柄，便于直接断言落库结果。"""

    return get_store()


@pytest.fixture()
def fake_repositories(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    """把服务层用到的 Repository 换成内存实现。

    替换的是服务模块命名空间里的类引用，服务代码无需任何改动。
    换上之后，服务层用例不再依赖 PostgreSQL。
    """

    monkeypatch.setattr("app.service.auth_service.UserRepository", FakeUserRepository)
    # 鉴权依赖也走 Repository 取用户，不替换就会在 HTTP 层掉回真实数据库
    monkeypatch.setattr("app.core.deps.UserRepository", FakeUserRepository)
    monkeypatch.setattr(
        "app.service.conversation_service.ConversationRepository", FakeConversationRepository
    )
    monkeypatch.setattr("app.service.conversation_service.MessageRepository", FakeMessageRepository)
    # chat_service 各自 import 了一份 Repository，绑定在它自己的命名空间里，
    # 必须单独替换，否则它会绕回真实数据库。
    monkeypatch.setattr(
        "app.service.chat_service.ConversationRepository", FakeConversationRepository
    )
    monkeypatch.setattr("app.service.chat_service.MessageRepository", FakeMessageRepository)
    monkeypatch.setattr("app.service.document_service.DocumentRepository", FakeDocumentRepository)
    monkeypatch.setattr("app.service.document_service.ChunkRepository", FakeChunkRepository)
    return get_store()


@pytest.fixture()
def fake_session() -> FakeSession:
    """Session 替身：Repository 已换成内存实现，只保留 commit/refresh 语义。

    不返回 Mock 是为了让「服务层绕过 Repository 直连数据库」这种情况立刻抛
    AttributeError，而不是被 Mock 静默吞掉。
    """

    return FakeSession()


@pytest.fixture()
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> FakeCache:
    """把服务层用到的缓存换成内存替身，使缓存行为可确定性断言。"""

    stub: FakeCache = FakeCache()
    monkeypatch.setattr("app.service.chat_service.cache", stub)
    monkeypatch.setattr("app.service.document_service.cache", stub)
    return stub


# ── 业务夹具 ──────────────────────────────────────────────────


@pytest.fixture()
def make_user():
    """工厂：创建一个已哈希密码的用户，返回 ORM 实例（写入内存库）。"""

    def _make(username: str, password: str = "123456") -> User:
        return FakeUserRepository().create(
            username=username,
            hashed_password=hash_password(password),
        )

    return _make


@pytest.fixture()
def alice(make_user) -> User:
    """用户 A。"""

    return make_user("alice")


@pytest.fixture()
def bob(make_user) -> User:
    """用户 B，用于验证跨用户隔离。"""

    return make_user("bob")


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    """注册并登录，返回带 Bearer token 的请求头。"""

    username: str = "tester"
    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    assert resp.status_code == 200, resp.text
    token: str = str(resp.json()["data"]["access_token"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def alice_conversation(alice: User) -> Conversation:
    """用户 A 的一个会话（写入内存库）。"""

    return FakeConversationRepository().create(user_id=alice.id, title="alice 的会话")


@pytest.fixture()
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把上传目录重定向到临时目录，并把体积上限设为 1MB。

    服务层与 HTTP 层都需要它：前者直接调用 upload，后者经由 multipart 表单。
    """

    from app.service import document_service as document_service_module

    target: Path = tmp_path / "uploads"
    target.mkdir()
    monkeypatch.setattr(
        document_service_module,
        "settings",
        SimpleNamespace(upload_dir=str(target), max_upload_size_mb=1),
    )
    return target


# ── 按目录自动打标记 ──────────────────────────────────────────


def pytest_collection_modifyitems(config, items) -> None:  # type: ignore[no-untyped-def]
    """按测试所在目录自动打标记，支持 `pytest -m unit` 分层运行。

    unit / service / http 都不需要外部服务（数据库与 Redis 均被替身替换），
    integration 才需要真实 PostgreSQL。这样没有 Docker 的机器上也能跑前四层。
    """

    tests_root: Path = Path(__file__).resolve().parent
    for item in items:
        relative = Path(str(item.fspath)).relative_to(tests_root)
        layer: str = relative.parts[0] if len(relative.parts) > 1 else ""
        if layer in {"unit", "service", "http", "integration"}:
            item.add_marker(getattr(pytest.mark, layer))
