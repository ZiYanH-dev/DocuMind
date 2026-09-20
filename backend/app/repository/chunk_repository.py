"""文档分块仓库（含向量检索，以及关键词检索所需的语料读取）。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk

# 语料为空时的指纹，与 retrieval.keyword.EMPTY_FINGERPRINT 取值一致
_EMPTY_FINGERPRINT = "empty"


class ChunkRepository:
    """文档分块表数据访问。"""

    def __init__(self, db: Session) -> None:
        self._db: Session = db

    def create_many(self, chunks: list[DocumentChunk]) -> None:
        """批量创建分块。"""

        self._db.add_all(chunks)
        self._db.commit()

    def vector_search(
        self,
        user_id: int,
        embedding: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, object]]:
        """基于 pgvector 余弦相似度搜索最相关的分块（ORM 向量表达式）。

        传入 score_threshold 时在 SQL 层过滤低分片段，避免无关上下文进入生成阶段。
        返回字段: chunk_id, document_id, document_title, chunk_index, content, score
        """

        distance = DocumentChunk.embedding.cosine_distance(embedding)
        statement = (
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id,
                Document.title.label("document_title"),
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                (1 - distance).label("score"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.user_id == user_id)
            .where(DocumentChunk.embedding.isnot(None))
        )

        if score_threshold is not None:
            statement = statement.where((1 - distance) >= score_threshold)

        statement = statement.order_by(distance).limit(top_k)
        rows = self._db.execute(statement).mappings().all()
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "document_title": row["document_title"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": float(row["score"]),
            }
            for row in rows
        ]

    def list_all_by_user(self, user_id: int) -> list[dict[str, object]]:
        """取出某用户全部分块，供 BM25 建立索引。

        这是一次全量读取，只在索引缓存未命中时调用；按 id 排序保证语料顺序稳定。
        """

        statement = (
            select(
                DocumentChunk.id.label("chunk_id"),
                DocumentChunk.document_id,
                Document.title.label("document_title"),
                DocumentChunk.chunk_index,
                DocumentChunk.content,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.user_id == user_id)
            .order_by(DocumentChunk.id)
        )
        return [
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "document_title": row["document_title"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
            }
            for row in self._db.execute(statement).mappings().all()
        ]

    def corpus_fingerprint(self, user_id: int) -> str:
        """语料指纹：分块数量与 id 范围，用于判断 BM25 索引是否需要重建。

        只做聚合查询，不读取正文，因此可以被高频调用。
        """

        statement = (
            select(
                func.count(DocumentChunk.id),
                func.min(DocumentChunk.id),
                func.max(DocumentChunk.id),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.user_id == user_id)
        )
        total, min_id, max_id = self._db.execute(statement).one()
        if not total:
            return _EMPTY_FINGERPRINT
        return f"{total}:{min_id}:{max_id}"
