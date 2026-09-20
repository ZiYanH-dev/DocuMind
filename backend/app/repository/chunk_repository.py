"""文档分块仓库（含向量检索）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk


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
        返回字段: document_id, document_title, chunk_index, content, score
        """

        distance = DocumentChunk.embedding.cosine_distance(embedding)
        statement = (
            select(
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
                "document_id": row["document_id"],
                "document_title": row["document_title"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "score": float(row["score"]),
            }
            for row in rows
        ]
