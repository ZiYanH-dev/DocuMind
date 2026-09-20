"""数据库连接与会话管理。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import settings

engine = create_engine(settings.resolved_database_url, pool_pre_ping=True, echo=settings.app_debug)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：获取数据库会话。"""

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
