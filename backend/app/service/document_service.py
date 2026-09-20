"""文档服务：上传、解析、向量化、删除。"""

from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config.embedding_client import embedding_service
from app.config.settings import settings
from app.core.cache import (
    DOCUMENT_LIST_TTL_SECONDS,
    cache,
    document_list_key,
    user_document_list_prefix,
    user_retrieval_prefix,
)
from app.core.logger import logger
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.repository.chunk_repository import ChunkRepository
from app.repository.document_repository import DocumentRepository
from app.schemas.document import DocumentListOut, DocumentOut
from app.utils.document_parser import document_parser

ALLOWED_FILE_TYPES: set[str] = {"pdf", "docx", "txt"}


class DocumentService:
    """文档业务逻辑。"""

    def __init__(self, db: Session) -> None:
        self._repository: DocumentRepository = DocumentRepository(db)
        self._chunk_repository: ChunkRepository = ChunkRepository(db)

    def upload(self, user: User, file: UploadFile) -> DocumentOut:
        """上传文档并异步处理（解析→分块→向量化）。"""

        file_name: str = file.filename or "unnamed"
        file_type: str = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if file_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型: {file_type}，仅支持 {', '.join(sorted(ALLOWED_FILE_TYPES))}",
            )

        content: bytes = file.file.read()
        if len(content) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件大小超过限制（{settings.max_upload_size_mb}MB）",
            )

        upload_dir: Path = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path: Path = upload_dir / f"{user.id}_{file_name}"
        file_path.write_bytes(content)

        document: Document = self._repository.create(
            user_id=user.id,
            title=Path(file_name).stem,
            file_name=file_name,
            file_path=str(file_path),
            file_size=len(content),
            file_type=file_type,
        )

        try:
            self._process_document(document)
        except Exception as exc:
            logger.exception("document process failed, user_id=%s doc_id=%s", user.id, document.id)
            self._repository.update_status(document.id, "failed", str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"文档处理失败: {exc}",
            ) from exc

        logger.info(
            "upload ok, user_id=%s doc_id=%s title=%s", user.id, document.id, document.title
        )
        cache.delete_prefix(user_document_list_prefix(user.id))
        return DocumentOut.model_validate(document)

    def list_documents(self, user: User, skip: int, limit: int) -> DocumentListOut:
        """查询用户文档列表，命中 Redis 缓存时直接返回。"""

        key: str = document_list_key(user.id, skip, limit)
        cached: Any = cache.get_json(key)
        if cached is not None:
            logger.info("document list cache hit, user_id=%s", user.id)
            return DocumentListOut.model_validate(cached)

        documents: list[Document] = self._repository.list_by_user_id(user.id, skip, limit)
        total: int = self._repository.count_by_user_id(user.id)
        result: DocumentListOut = DocumentListOut(
            total=total,
            items=[DocumentOut.model_validate(doc) for doc in documents],
        )
        cache.set_json(key, result.model_dump(mode="json"), DOCUMENT_LIST_TTL_SECONDS)
        return result

    def delete_document(self, user: User, document_id: int) -> None:
        """删除文档（含分块与文件）。"""

        document: Document | None = self._repository.get_by_user_id(user.id, document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            )
        file_path: Path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()
        self._repository.delete(document)
        cache.delete_prefix(user_document_list_prefix(user.id))
        cache.delete_prefix(user_retrieval_prefix(user.id))
        logger.info("document deleted, user_id=%s doc_id=%s", user.id, document_id)

    def _process_document(self, document: Document) -> None:
        """解析文档 → 分块 → 向量化 → 入库。"""

        text: str = document_parser.parse(document.file_path, document.file_type)
        chunks: list[str] = document_parser.split(text)
        if not chunks:
            raise ValueError("文档内容为空，无法分块")

        embeddings: list[list[float]] = embedding_service.embed_texts(chunks)
        chunk_models: list[DocumentChunk] = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk_text,
                embedding=embedding,
            )
            for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        self._chunk_repository.create_many(chunk_models)
        self._repository.update_status(document.id, "completed")
        logger.info("document indexed, doc_id=%s chunks=%d", document.id, len(chunks))
