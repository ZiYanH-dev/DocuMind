"""缓存层单元测试。

两个重点：
1. key 的命名规则 —— 前缀批量失效依赖它，改错会导致缓存清不干净。
2. Redis 故障降级 —— 缓存挂掉不能拖垮主链路。
"""

from __future__ import annotations

import json

import pytest
from redis.exceptions import RedisError

from app.core.cache import (
    DOCUMENT_LIST_PREFIX,
    HISTORY_PREFIX,
    RETRIEVAL_PREFIX,
    RedisCache,
    document_list_key,
    history_key,
    retrieval_key,
    user_document_list_prefix,
    user_retrieval_prefix,
)


class _FakeRedis:
    """内存版 Redis 替身，按 need_fail 开关模拟故障。"""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.fail: bool = fail

    def _guard(self) -> None:
        if self.fail:
            raise RedisError("redis is down")

    def get(self, key: str) -> str | None:
        self._guard()
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._guard()
        self.store[key] = value

    def delete(self, *keys: str) -> None:
        self._guard()
        for key in keys:
            self.store.pop(key, None)

    def scan_iter(self, match: str, count: int = 100):
        self._guard()
        prefix: str = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


# ── key 命名 ──────────────────────────────────────────────────


def test_history_key_namespaces_by_conversation() -> None:
    """历史缓存按会话隔离。"""

    assert history_key(7) == f"{HISTORY_PREFIX}:7"
    assert history_key(7) != history_key(8)


def test_retrieval_key_hashes_long_query() -> None:
    """长查询做摘要，避免 key 过长且能稳定命中。"""

    long_query: str = "线程" * 500
    key: str = retrieval_key(1, long_query)

    assert len(key) < 100
    assert key.startswith(f"{RETRIEVAL_PREFIX}:1:")
    assert key == retrieval_key(1, long_query)


def test_retrieval_key_separates_users_and_queries() -> None:
    """不同用户、不同查询的 key 必须不同。"""

    assert retrieval_key(1, "a") != retrieval_key(2, "a")
    assert retrieval_key(1, "a") != retrieval_key(1, "b")


def test_user_prefixes_match_key_format() -> None:
    """批量失效的前缀必须能覆盖到对应 key，否则缓存清不掉。"""

    assert retrieval_key(1, "a").startswith(user_retrieval_prefix(1))
    assert document_list_key(1, 0, 20).startswith(user_document_list_prefix(1))
    assert not retrieval_key(2, "a").startswith(user_retrieval_prefix(1))


def test_document_list_key_includes_pagination() -> None:
    """列表缓存带分页参数，不同页互不覆盖。"""

    assert document_list_key(1, 0, 20) != document_list_key(1, 20, 20)


# ── 正常读写 ──────────────────────────────────────────────────


def test_set_then_get_roundtrip() -> None:
    """写入后能读回等价对象。"""

    cache: RedisCache = RedisCache(_FakeRedis())
    cache.set_json("k", {"a": 1}, ttl=60)

    assert cache.get_json("k") == {"a": 1}


def test_missing_key_returns_none() -> None:
    """key 不存在时返回 None，调用方据此回源。"""

    assert RedisCache(_FakeRedis()).get_json("nope") is None


def test_non_json_value_returns_none() -> None:
    """缓存里被写入了非 JSON 内容时返回 None，而不是抛异常。"""

    fake = _FakeRedis()
    fake.store["k"] = "not json"
    fake.fail = False

    assert RedisCache(fake).get_json("k") is None


def test_delete_prefix_removes_only_matching_keys() -> None:
    """按前缀清理只删匹配的 key。"""

    fake = _FakeRedis()
    cache: RedisCache = RedisCache(fake)
    cache.set_json(f"{DOCUMENT_LIST_PREFIX}:1:0:20", {"a": 1})
    cache.set_json(f"{DOCUMENT_LIST_PREFIX}:2:0:20", {"a": 1})
    cache.set_json(f"{HISTORY_PREFIX}:1", [{"role": "user"}])

    cache.delete_prefix(f"{DOCUMENT_LIST_PREFIX}:1:")

    assert cache.get_json(f"{DOCUMENT_LIST_PREFIX}:1:0:20") is None
    assert cache.get_json(f"{DOCUMENT_LIST_PREFIX}:2:0:20") == {"a": 1}
    assert cache.get_json(f"{HISTORY_PREFIX}:1") is not None


def test_delete_with_no_key_is_noop() -> None:
    """不传 key 时直接返回，不发起 Redis 调用。"""

    fake = _FakeRedis()
    RedisCache(fake).delete()

    assert fake.store == {}


def test_json_preserves_non_ascii() -> None:
    """中文内容写入后能原样读回，不被转义成 \\uXXXX 后失真。"""

    cache: RedisCache = RedisCache(_FakeRedis())
    cache.set_json("k", {"content": "线程是调度单位"})

    assert cache.get_json("k")["content"] == "线程是调度单位"

    raw: str = next(iter(cache._client.store.values()))
    assert json.loads(raw)["content"] == "线程是调度单位"


# ── 故障降级 ──────────────────────────────────────────────────


@pytest.fixture()
def broken_cache() -> RedisCache:
    """Redis 不可用时的缓存实例。"""

    return RedisCache(_FakeRedis(fail=True))


def test_get_degrades_to_none_on_redis_error(broken_cache: RedisCache) -> None:
    """读失败降级为未命中，走回源逻辑。"""

    assert broken_cache.get_json("k") is None


def test_set_is_silent_on_redis_error(broken_cache: RedisCache) -> None:
    """写失败不能抛异常，否则会打断业务流程。"""

    broken_cache.set_json("k", {"a": 1})  # 不抛异常即通过


def test_delete_is_silent_on_redis_error(broken_cache: RedisCache) -> None:
    """删除失败静默跳过。"""

    broken_cache.delete("k")
    broken_cache.delete_prefix("prefix:")


def test_scan_failure_is_silent(broken_cache: RedisCache) -> None:
    """SCAN 失败时静默跳过。"""

    broken_cache.delete_prefix("documind:")
