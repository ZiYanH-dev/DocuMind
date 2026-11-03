"""文档服务测试（内存库 + 临时目录，不需要数据库）。

上传目录被重定向到 tmp_path，避免测试污染 var/uploads。
断言只针对行为（异常消息），不绑定异常类型。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.models.user import User
from app.service.document_service import DocumentService
from tests.fakes import FakeDocumentRepository, FakeSession, MemoryStore


@pytest.fixture()
def service(
    upload_dir: Path, fake_repositories: MemoryStore, fake_session: FakeSession
) -> DocumentService:
    """文档服务实例（Repository 已被换成内存实现）。"""

    return DocumentService(fake_session)


def _file(name: str, content: bytes) -> UploadFile:
    """构造上传文件对象。"""

    return UploadFile(file=io.BytesIO(content), filename=name)


# ── 上传成功 ──────────────────────────────────────────────────


def test_upload_txt_creates_completed_document(service: DocumentService, alice: User) -> None:
    """上传 TXT 后状态变为 completed，标题取文件名主干。"""

    out = service.upload(alice, _file("rag.txt", "RAG 是检索增强生成。".encode()))

    assert out.title == "rag"
    assert out.file_name == "rag.txt"
    assert out.status == "completed"


def test_upload_creates_chunks(service: DocumentService, alice: User) -> None:
    """上传后必须产生分块，否则检索永远为空。"""

    out = service.upload(alice, _file("rag.txt", "RAG 是检索增强生成。".encode()))

    assert FakeDocumentRepository().count_chunks(out.id) > 0


def test_upload_persists_file_on_disk(
    service: DocumentService, alice: User, upload_dir: Path
) -> None:
    """源文件真实落盘。"""

    service.upload(alice, _file("rag.txt", b"hello"))

    assert list(upload_dir.iterdir())


def test_same_filename_twice_keeps_both_files(
    service: DocumentService, alice: User, upload_dir: Path
) -> None:
    """同名文件重复上传应各占一个源文件。

    回归背景：早期按原名落盘，第二次上传会覆盖第一次的源文件，
    删除其中一条文档会连带删掉另一条的文件。
    """

    service.upload(alice, _file("same.txt", "第一版".encode()))
    service.upload(alice, _file("same.txt", "第二版".encode()))

    assert len(list(upload_dir.iterdir())) == 2
    assert service.list_documents(alice, skip=0, limit=20).total == 2


def test_upload_sanitizes_path_traversal_filename(
    service: DocumentService, alice: User, upload_dir: Path
) -> None:
    """文件名里的路径穿越必须被剥掉，不能写到上传目录之外。"""

    service.upload(alice, _file("../../evil.txt", b"x"))

    for path in upload_dir.iterdir():
        assert path.parent == upload_dir


# ── 上传校验 ──────────────────────────────────────────────────


@pytest.mark.parametrize("filename", ["a.exe", "a.zip", "noext"])
def test_upload_rejects_unsupported_type(
    service: DocumentService, alice: User, filename: str
) -> None:
    """白名单之外的类型必须拒绝。"""

    with pytest.raises(Exception, match="不支持的文件类型"):
        service.upload(alice, _file(filename, b"x"))


def test_upload_rejects_oversized_file(service: DocumentService, alice: User) -> None:
    """超过体积上限的文件必须拒绝（上限已被 fixture 设为 1MB）。"""

    with pytest.raises(Exception, match="超过限制"):
        service.upload(alice, _file("big.txt", b"x" * (1024 * 1024 + 1)))


def test_upload_marks_failed_when_content_empty(service: DocumentService, alice: User) -> None:
    """内容为空的文档应处理失败，而不是留下一条 completed 的空文档。"""

    with pytest.raises(Exception):
        service.upload(alice, _file("blank.txt", b"   \n\t  "))

    documents = FakeDocumentRepository().list_by_user_id(alice.id)
    assert documents
    assert documents[0].status == "failed"


# ── 列表与删除 ────────────────────────────────────────────────


def test_list_returns_only_own_documents(service: DocumentService, alice: User, bob: User) -> None:
    """用户只能看到自己上传的文档。"""

    service.upload(alice, _file("alice.txt", b"a"))
    service.upload(bob, _file("bob.txt", b"b"))

    result = service.list_documents(alice, skip=0, limit=20)

    assert [item.title for item in result.items] == ["alice"]


def test_delete_removes_document_and_file(
    service: DocumentService, alice: User, upload_dir: Path
) -> None:
    """删除文档时同时删除源文件，避免留下孤儿文件。"""

    out = service.upload(alice, _file("rag.txt", b"hello"))
    service.delete_document(alice, out.id)

    assert service.list_documents(alice, skip=0, limit=20).total == 0
    assert list(upload_dir.iterdir()) == []


def test_delete_cascades_chunks(service: DocumentService, alice: User, store: MemoryStore) -> None:
    """删除文档时级联删除分块，与外键 ondelete=CASCADE 行为一致。"""

    out = service.upload(alice, _file("rag.txt", "内容".encode()))
    service.delete_document(alice, out.id)

    assert store.chunks == {}


def test_delete_rejects_other_users_document(
    service: DocumentService, alice: User, bob: User
) -> None:
    """越权删除他人文档必须被拒绝。"""

    out = service.upload(alice, _file("alice.txt", b"a"))

    with pytest.raises(Exception, match="文档不存在"):
        service.delete_document(bob, out.id)

    assert service.list_documents(alice, skip=0, limit=20).total == 1


def test_delete_nonexistent_document(service: DocumentService, alice: User) -> None:
    """删除不存在的文档给出明确报错。"""

    with pytest.raises(Exception, match="文档不存在"):
        service.delete_document(alice, 999999)
