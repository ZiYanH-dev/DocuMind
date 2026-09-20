"""Redis 连接池管理：全局客户端与 FastAPI 依赖。"""

from collections.abc import Generator

import redis

from app.config.settings import settings

redis_client = redis.Redis.from_url(
    settings.resolved_redis_url, decode_responses=True
)


def get_redis() -> Generator[redis.Redis, None, None]:
    """FastAPI 依赖：获取 Redis 客户端。"""

    yield redis_client
