"""FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import api_router
from app.config.settings import settings
from app.core.exceptions import register_exception_handlers
from app.core.logger import logger
from app.core.middleware import register_middleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动与关停日志。"""

    logger.info(
        "Starting %s v%s (env=%s)", settings.app_name, "0.1.0", settings.app_env
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 智能学习助手 - 基于知识库的智能问答系统",
    debug=settings.app_debug,
    lifespan=lifespan,
)

register_middleware(app)
register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
def health_check() -> dict[str, str]:
    """健康检查。"""

    return {"status": "ok"}
