"""文档 API 的 HTTP 行为测试（不连数据库，上传目录重定向到 tmp_path）。

这一层额外守 multipart 表单契约：字段名、文件类型校验的返回码与提示。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

DOCUMENTS = "/api/v1/documents"
UPLOAD = f"{DOCUMENTS}/upload"


def _login_headers(client: TestClient, username: str) -> dict[str, str]:
    """注册并登录指定用户，返回请求头。"""

    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _upload(
    client: TestClient,
    headers: dict[str, str],
    filename: str = "rag.txt",
    content: bytes = b"RAG is retrieval augmented generation.",
    content_type: str = "text/plain",
):
    """以 multipart 表单上传一个文件。"""

    return client.post(
        UPLOAD,
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


# ── 上传 ──────────────────────────────────────────────────────


def test_upload_returns_completed_document(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """上传成功后返回 completed 状态与文件名主干标题。"""

    response = _upload(api_client, auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert body["data"]["title"] == "rag"
    assert body["data"]["file_name"] == "rag.txt"


def test_upload_writes_file_to_upload_dir(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """源文件落在配置的上传目录内。"""

    _upload(api_client, auth_headers)

    files = list(upload_dir.iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == b"RAG is retrieval augmented generation."


def test_upload_rejects_unsupported_type(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """白名单外类型返回 400，提示里带上支持列表。"""

    response = _upload(api_client, auth_headers, filename="evil.exe", content=b"MZ")

    assert response.status_code == 400
    message: str = response.json()["message"]
    assert "不支持的文件类型" in message
    assert "pdf" in message


def test_upload_rejects_oversized_file(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """超出体积上限返回 400（上限已被 fixture 设为 1MB）。"""

    response = _upload(api_client, auth_headers, content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 400
    assert "超过限制" in response.json()["message"]


def test_upload_without_file_field_returns_422(
    api_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """表单里没有 file 字段时返回 422，而不是 500。"""

    response = api_client.post(UPLOAD, data={"note": "x"}, headers=auth_headers)

    assert response.status_code == 422


def test_upload_requires_auth(api_client: TestClient, upload_dir: Path) -> None:
    """未登录上传返回 401。"""

    assert _upload(api_client, {}).status_code == 401


# ── 列表与删除 ────────────────────────────────────────────────


def test_list_documents_returns_own_only(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """列表只包含自己上传的文档。"""

    _upload(api_client, auth_headers, filename="mine.txt")
    other = _login_headers(api_client, "bob")
    _upload(api_client, other, filename="theirs.txt")

    body = api_client.get(DOCUMENTS, headers=auth_headers).json()

    assert body["data"]["total"] == 1
    assert [item["title"] for item in body["data"]["items"]] == ["mine"]


def test_delete_document_removes_file(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """删除文档同时清理源文件，不留孤儿文件。"""

    document_id = _upload(api_client, auth_headers).json()["data"]["id"]

    response = api_client.delete(f"{DOCUMENTS}/{document_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == document_id
    assert list(upload_dir.iterdir()) == []
    assert api_client.get(DOCUMENTS, headers=auth_headers).json()["data"]["total"] == 0


def test_delete_rejects_other_users_document(
    api_client: TestClient, auth_headers: dict[str, str], upload_dir: Path
) -> None:
    """越权删除返回 404，且对方文档仍然存在。"""

    document_id = _upload(api_client, auth_headers).json()["data"]["id"]
    other = _login_headers(api_client, "bob")

    response = api_client.delete(f"{DOCUMENTS}/{document_id}", headers=other)

    assert response.status_code == 404
    assert response.json()["message"] == "文档不存在"
    assert api_client.get(DOCUMENTS, headers=auth_headers).json()["data"]["total"] == 1


def test_delete_nonexistent_document(api_client: TestClient, auth_headers: dict[str, str]) -> None:
    """删除不存在的文档返回 404。"""

    assert api_client.delete(f"{DOCUMENTS}/999999", headers=auth_headers).status_code == 404


def test_documents_require_auth(api_client: TestClient) -> None:
    """未带令牌一律 401。"""

    assert api_client.get(DOCUMENTS).status_code == 401
    assert api_client.delete(f"{DOCUMENTS}/1").status_code == 401
