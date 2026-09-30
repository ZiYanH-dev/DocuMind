"""测试夹具：复用本地 PostgreSQL（docker 端口 5433）的独立测试库。"""

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://documind:documind_123@localhost:5433/documind_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6380/1")
# 测试环境允许缺失真实 LLM Key；ChatAPI 调用需真实 Key 或 mock（见测试说明）。
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.database import Base
from app.config.embedding_client import EmbeddingService as _EmbeddingService
from app.config.settings import settings
from app.main import app


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch) -> None:
    """离线替掉真实 Embedding API，避免测试依赖网络/密钥（mock 掉 embed_texts）。

    维度取 settings.embedding_dim，与 document_chunks.embedding 列保持一致，
    避免迁移调整维度后这里写死的旧值导致入库失败。
    """

    def _fake_embed_texts(self, texts, *args, **kwargs):
        return [[0.0] * settings.embedding_dim for _ in texts]

    monkeypatch.setattr(_EmbeddingService, "embed_texts", _fake_embed_texts)


from app.core.deps import get_db  # noqa: E402 —— 必须在设置环境变量之后再导入

TEST_DATABASE_URL: str = os.environ["DATABASE_URL"]
ENGINE = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


@pytest.fixture(scope="session")
def _prepare_db() -> None:
    """准备测试库：确保数据库存在并重建全部表。"""

    # 测试库可能不存在，先尝试连接；失败则跳过（需手动 createdb）。
    try:
        with ENGINE.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "无法连接测试数据库，请确认 docker 已启动且存在库 documind_test"
        ) from exc
    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)
    yield
    Base.metadata.drop_all(ENGINE)


@pytest.fixture()
def db_session(_prepare_db) -> Session:
    """提供干净的会话（每次测试独立事务回滚）。"""

    connection = ENGINE.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    """TestClient，覆盖 get_db 依赖以使用测试会话。"""

    def _override_get_db() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
