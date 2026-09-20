"""文档 API 路由。"""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.document import DocumentListOut, DocumentOut
from app.schemas.response import ApiResponse, DeleteOut
from app.service.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["文档"])


@router.post("/upload", response_model=ApiResponse[DocumentOut])
def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentOut]:
    """上传文档（支持 PDF / Word / TXT）。"""

    service: DocumentService = DocumentService(db)
    return ApiResponse(data=service.upload(current_user, file))


@router.get("", response_model=ApiResponse[DocumentListOut])
def list_documents(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DocumentListOut]:
    """获取文档列表。"""

    service: DocumentService = DocumentService(db)
    return ApiResponse(data=service.list_documents(current_user, skip, limit))


@router.delete("/{document_id}", response_model=ApiResponse[DeleteOut], status_code=200)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[DeleteOut]:
    """删除文档。"""

    service: DocumentService = DocumentService(db)
    service.delete_document(current_user, document_id)
    return ApiResponse(data=DeleteOut(id=document_id))
