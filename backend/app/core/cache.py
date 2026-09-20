"""Redis 缓存封装：统一 key 命名、JSON 序列化与故障降级。

所有读写方法在 Redis 不可用时静默降级，读返回 None、写与删除直接跳过，
保证缓存层故障不影响主链路。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.config.redis import redis_client
from app.core.logger import logger

# ── key 命名空间 ──────────────────────────────────────────────

HISTORY_PREFIX: str = "study:history"
RETRIEVAL_PREFIX: str = "study:retrieval"
DOCUMENT_LIST_PREFIX: str = "study:document:list"

# ── 过期时间（秒）─────────────────────────────────────────────

HISTORY_TTL_SECONDS: int = 600
RETRIEVAL_TTL_SECONDS: int = 300
DOCUMENT_LIST_TTL_SECONDS: int = 120


class RedisCache:
    """Redis 读写封装。"""

    def __init__(self, client: Redis) -> None:
        self._client: Redis = client

    def get_json(self, key: str) -> Any | None:
        """读取并反序列化 JSON 值，key 不存在或 Redis 异常时返回 None。"""

        try:
            raw: str | None = self._client.get(key)
        except RedisError as exc:
            logger.warning("cache get failed, key=%s err=%s", key, exc)
            return None

        if raw is None:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("cache value not json, key=%s", key)
            return None

    def set_json(self, key: str, value: Any, ttl: int = HISTORY_TTL_SECONDS) -> None:
        """序列化为 JSON 写入并设置过期时间。"""

        try:
            self._client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        except (RedisError, TypeError) as exc:
            logger.warning("cache set failed, key=%s err=%s", key, exc)

    def delete(self, *keys: str) -> None:
        """删除指定 key，传入空列表时直接返回。"""

        if not keys:
            return

        try:
            self._client.delete(*keys)
        except RedisError as exc:
            logger.warning("cache delete failed, keys=%s err=%s", keys, exc)

    def delete_prefix(self, prefix: str) -> None:
        """按前缀批量删除，用 SCAN 游标遍历避免 KEYS 阻塞 Redis。"""

        try:
            for key in self._client.scan_iter(match=f"{prefix}*", count=100):
                self._client.delete(key)
        except RedisError as exc:
            logger.warning("cache delete_prefix failed, prefix=%s err=%s", prefix, exc)


cache: RedisCache = RedisCache(redis_client)


def history_key(conversation_id: int) -> str:
    """会话历史缓存 key。"""

    return f"{HISTORY_PREFIX}:{conversation_id}"


def retrieval_key(user_id: int, query: str) -> str:
    """检索结果缓存 key，查询语句取 sha1 摘要避免 key 过长。"""

    digest: str = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return f"{RETRIEVAL_PREFIX}:{user_id}:{digest}"


def user_retrieval_prefix(user_id: int) -> str:
    """某用户全部检索结果缓存的前缀，用于批量失效。"""

    return f"{RETRIEVAL_PREFIX}:{user_id}:"


def document_list_key(user_id: int, skip: int, limit: int) -> str:
    """文档列表缓存 key。"""

    return f"{DOCUMENT_LIST_PREFIX}:{user_id}:{skip}:{limit}"


def user_document_list_prefix(user_id: int) -> str:
    """某用户全部文档列表缓存的前缀，用于批量失效。"""

    return f"{DOCUMENT_LIST_PREFIX}:{user_id}:"
