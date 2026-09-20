"""中间件模块。"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.config.settings import settings
from app.core.logger import logger


def register_middleware(app: FastAPI) -> None:
    """注册全局中间件。"""

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求耗时日志中间件
    @app.middleware("http")
    async def log_request_duration(request: Request, call_next) -> Response:
        start_time: float = time.time()

        response: Response = await call_next(request)

        duration: float = (time.time() - start_time) * 1000
        logger.info(
            "%s %s -> %s in %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response
