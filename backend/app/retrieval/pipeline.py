"""检索流水线 —— 把多路召回、融合、重排串成一次检索。

单次检索的步骤：
1. 查询改写，得到原问题与若干变体；
2. 每个查询分别走向量召回与关键词召回；
3. 所有路的结果做倒数排名融合；
4. 对融合后的候选做重排，取最终 top_k。

每一路都可以通过配置关闭，关闭后自动退化为对应的简化链路：
单独关掉重排即退化为混合召回，关键词与重排都关掉即退化为纯向量检索。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config.embedding_client import embedding_service
from app.config.settings import settings
from app.core.cache import RETRIEVAL_TTL_SECONDS, cache, retrieval_key
from app.repository.chunk_repository import ChunkRepository
from app.retrieval.fusion import rrf_fuse
from app.retrieval.keyword import KeywordRetriever
from app.retrieval.rerank import rerank
from app.retrieval.rewrite import rewrite_queries

logger = logging.getLogger(__name__)


def retrieve(
    session: Session,
    user_id: int,
    question: str,
    *,
    top_k: int | None = None,
    use_cache: bool = True,
) -> list[dict[str, object]]:
    """执行一次完整检索，返回按相关度降序的片段。

    结果按用户与问题文本缓存，文档增删时由文档服务按前缀失效。
    评估脚本可以传 use_cache=False 以测出真实耗时与效果。
    """

    limit = top_k or settings.vector_top_k
    cache_key = retrieval_key(user_id, question)

    if use_cache:
        cached = cache.get_json(cache_key)
        if cached is not None:
            logger.info("retrieval cache hit, user_id=%s", user_id)
            return [dict(item) for item in cached]

    chunk_repo = ChunkRepository(session)
    queries = [question]
    if settings.rewrite_enabled:
        queries.extend(rewrite_queries(question, settings.rewrite_count))

    rankings: list[list[dict[str, object]]] = []
    for query in queries:
        rankings.append(_vector_recall(chunk_repo, user_id, query))
        if settings.keyword_enabled:
            rankings.append(_keyword_recall(chunk_repo, user_id, query))

    fused = rrf_fuse(rankings, k=settings.fusion_k)
    if settings.rerank_enabled and fused:
        results = rerank(question, fused, top_n=limit)
    else:
        results = fused[:limit]

    if use_cache:
        cache.set_json(cache_key, results, RETRIEVAL_TTL_SECONDS)
    return results


def _vector_recall(
    chunk_repo: ChunkRepository,
    user_id: int,
    query: str,
) -> list[dict[str, object]]:
    """向量召回：把查询向量化后在 pgvector 上按余弦距离取前若干条。"""

    embedding = embedding_service.embed_query(query)
    rows = chunk_repo.vector_search(
        user_id,
        embedding,
        top_k=settings.vector_recall_k,
        score_threshold=settings.vector_score_threshold,
    )
    return [{**row, "recall": "vector"} for row in rows]


def _keyword_recall(
    chunk_repo: ChunkRepository,
    user_id: int,
    query: str,
) -> list[dict[str, object]]:
    """关键词召回：在按用户缓存的 BM25 索引上打分取前若干条。"""

    retriever = KeywordRetriever(
        chunk_repo.corpus_fingerprint,
        chunk_repo.list_all_by_user,
    )
    return retriever.search(user_id, query, settings.keyword_recall_k)
