"""文档仓库。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk


class DocumentRepository:
    """文档表数据访问。"""

    def __init__(self, db: Session) -> None:
        self._db: Session = db

    def create(
        self,
        user_id: int,
        title: str,
        file_name: str,
        file_path: str,
        file_size: int,
        file_type: str,
    ) -> Document:
        """创建文档记录。"""

        document = Document(
            user_id=user_id,
            title=title,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            status="processing",
        )
        self._db.add(document)
        self._db.commit()
        self._db.refresh(document)
        return document

    def get_by_id(self, document_id: int) -> Document | None:
        """按 ID 查询文档。"""

        return self._db.get(Document, document_id)

    def get_by_user_id(self, user_id: int, document_id: int) -> Document | None:
        """按用户 ID + 文档 ID 查询（校验归属）。"""

        return (
            self._db.query(Document)
            .filter(Document.user_id == user_id, Document.id == document_id)
            .first()
        )

    def list_by_user_id(self, user_id: int, skip: int = 0, limit: int = 100) -> list[Document]:
        """查询用户的文档列表（分页）。"""

        return (
            self._db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user_id(self, user_id: int) -> int:
        """统计用户的文档数量。"""

        return self._db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user_id)) or 0

    def count_chunks(self, document_id: int) -> int:
        """统计某个文档的分块数量。"""

        return (
            self._db.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
            )
            or 0
        )

    def update_status(self, document_id: int, status: str, error_message: str | None = None) -> None:
        """更新文档处理状态。"""

        document = self._db.get(Document, document_id)
        if document is not None:
            document.status = status
            document.error_message = error_message
            self._db.commit()

    def delete(self, document: Document) -> None:
        """删除文档（级联删除分块）。"""

        self._db.delete(document)
        self._db.commit()

    def delete_chunks_by_document_id(self, document_id: int) -> None:
        """删除文档的所有分块。"""

        self._db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        self._db.commit()
