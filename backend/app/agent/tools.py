"""Agent Tools — 将业务能力封装成 LLM 可调用的工具。

工具通过闭包捕获当前请求的数据库会话与用户 ID，并把结构化检索命中写入
调用方传入的收集器，供服务层生成可定位到文档与分块序号的引用来源。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.config.embedding_client import embedding_service
from app.config.settings import settings
from app.core.cache import RETRIEVAL_TTL_SECONDS, cache, retrieval_key
from app.repository.chunk_repository import ChunkRepository
from app.repository.document_repository import DocumentRepository
from app.schemas.chat import SourceInfo

logger = logging.getLogger(__name__)


# ── 闭包工具工厂 ──────────────────────────────────────────────


def build_tools(
    session: Session,
    user_id: int,
    hits: list[SourceInfo] | None = None,
) -> list[Any]:
    """根据用户和会话构建工具列表。

    每次请求构建一次，闭包捕获 session 与 user_id，向量检索天然按用户隔离。
    传入 hits 时，search_knowledge 会把每次结构化命中追加进去。
    """

    chunk_repo = ChunkRepository(session)
    doc_repo = DocumentRepository(session)
    hit_collector: list[SourceInfo] = hits if hits is not None else []

    def _load_chunks(query: str, top_k: int) -> list[dict[str, object]]:
        """优先读检索结果缓存，未命中再向量化并查询。"""

        key: str = retrieval_key(user_id, query)
        cached: Any = cache.get_json(key)
        if cached is not None:
            logger.info("retrieval cache hit, user_id=%s query_len=%d", user_id, len(query))
            return cached

        emb = embedding_service.embed_query(query)
        results: list[dict[str, object]] = chunk_repo.vector_search(
            user_id,
            emb,
            top_k=top_k,
            score_threshold=settings.vector_score_threshold,
        )
        cache.set_json(key, results, RETRIEVAL_TTL_SECONDS)
        return results

    def _record_hits(results: list[dict[str, object]]) -> None:
        """把检索结果转换成结构化命中，追加到收集器。"""

        for row in results:
            hit_collector.append(
                SourceInfo(
                    document_id=int(row["document_id"]),
                    document_title=str(row["document_title"] or "未知文档"),
                    chunk_index=int(row["chunk_index"]),
                    snippet=str(row["content"])[:200],
                    score=float(row["score"]),
                )
            )

    @tool
    def search_knowledge(query: str, top_k: int = settings.vector_top_k) -> str:
        """在用户上传的知识库中检索相关文档片段。

        当你需要回答与用户上传的资料、笔记相关的问题时使用此工具。
        如果用户没有上传任何文档，返回结果为空。

        Args:
            query: 搜索关键词或自然语言问题
            top_k: 返回的最相关文档数量，默认跟随检索配置
        """

        try:
            results = _load_chunks(query, top_k)

            if not results:
                return "知识库中未找到相关内容。"

            _record_hits(results)

            # 格式化为可读文本（LLM 易理解的格式）
            lines: list[str] = []
            for row in results:
                doc_title = row["document_title"] or "未知文档"
                lines.append(f"[来源: {doc_title}, 相关度: {float(row['score']):.2f}]")
                lines.append(str(row["content"]))
                lines.append("")

            return "\n".join(lines).strip()
        except Exception as e:
            logger.error("search_knowledge failed: %s", e)
            return f"检索出错了: {e}"

    @tool
    def list_documents() -> str:
        """列出用户上传的所有文档及其状态。

        当用户问"我上传了什么文档"、"帮我看看知识库"时使用。
        """

        try:
            docs = doc_repo.list_by_user_id(user_id)
            if not docs:
                return "你还没有上传任何文档。"

            lines: list[str] = ["你上传了以下文档："]
            for d in docs:
                lines.append(
                    f"  - {d.title} (ID:{d.id}, 状态:{d.status}, 分块数:{doc_repo.count_chunks(d.id)})"
                )
            return "\n".join(lines)
        except Exception as e:
            logger.error("list_documents failed: %s", e)
            return f"获取文档列表出错: {e}"

    return [search_knowledge, list_documents]
