"""关键词召回 —— 基于 BM25 的中文关键词检索。

向量召回按语义相似度取片段，对精确术语与专有名词不敏感；关键词召回按词频与
逆文档频率打分，正好补上这一块。两路并行召回后交给融合层合并。

BM25 的逆文档频率需要全量语料才能计算，因此索引按用户维度构建并缓存在进程内。
语料是否变化由调用方注入的轻量查询判断，缓存命中时不会产生全量取数据的开销。
文档发生增删时由文档服务调用 invalidate 让缓存立即过期。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# 索引缓存：user_id -> (语料指纹, BM25 索引, 语料)
_cache: dict[int, tuple[str, BM25Okapi, list[dict[str, object]]]] = {}
_lock = threading.Lock()

EMPTY_FINGERPRINT = "empty"


def tokenize(text: str) -> list[str]:
    """把文本切成检索词：中文按 jieba 分词，英文与数字转小写保留原形。

    jieba 会把空格与标点也作为独立 token 返回，这里统一过滤掉。
    """

    return [token.lower() for token in jieba.lcut(text) if token.strip()]


def invalidate(user_id: int) -> None:
    """让某用户的索引缓存失效，文档增删后调用。"""

    with _lock:
        _cache.pop(user_id, None)


def invalidate_all() -> None:
    """清空全部索引缓存。"""

    with _lock:
        _cache.clear()


class KeywordRetriever:
    """BM25 关键词召回器。

    load_fingerprint 用一次轻量查询给出语料指纹，load_chunks 才真正取出全部片段。
    两者都由调用方注入，检索模块因此不直接持有数据库会话。
    """

    def __init__(
        self,
        load_fingerprint: Callable[[int], str],
        load_chunks: Callable[[int], list[dict[str, object]]],
    ) -> None:
        self._load_fingerprint = load_fingerprint
        self._load_chunks = load_chunks

    def _get_index(self, user_id: int) -> tuple[BM25Okapi, list[dict[str, object]]] | None:
        """取该用户的 BM25 索引，语料发生变化时重建。"""

        fingerprint = self._load_fingerprint(user_id)
        if fingerprint == EMPTY_FINGERPRINT:
            return None

        with _lock:
            cached = _cache.get(user_id)
            if cached is not None and cached[0] == fingerprint:
                return cached[1], cached[2]

        chunks = self._load_chunks(user_id)
        if not chunks:
            return None

        corpus = [tokenize(str(chunk["content"])) for chunk in chunks]
        # 全部片段都切不出词时 BM25 无法建立，放弃关键词这一路
        if not any(corpus):
            return None

        index = BM25Okapi(corpus)
        with _lock:
            _cache[user_id] = (fingerprint, index, chunks)
        logger.info("keyword index built, user_id=%s chunks=%d", user_id, len(chunks))
        return index, chunks

    def search(self, user_id: int, query: str, top_k: int) -> list[dict[str, object]]:
        """返回按 BM25 分数降序的关键词召回结果，已按用户隔离。"""

        terms = tokenize(query)
        if not terms:
            return []

        loaded = self._get_index(user_id)
        if loaded is None:
            return []

        index, chunks = loaded
        scores = index.get_scores(terms)
        ranked = sorted(
            zip(scores, chunks, strict=True),
            key=lambda pair: float(pair[0]),
            reverse=True,
        )
        # 分数为 0 说明该片段与查询没有任何词重合，不纳入召回
        return [
            {**chunk, "score": float(score), "recall": "keyword"}
            for score, chunk in ranked[:top_k]
            if float(score) > 0
        ]
