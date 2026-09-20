"""主链路集成测试：注册 → 登录 → 上传 → 列表 → 删除。

说明：
- 本测试覆盖 HTTP 层到 Repository 层的全链路（不含真实 LLM/Embedding 调用）。
- 文档上传接口为同步处理，会真实调用 Embedding。若 .env 未配置可用
  Embedding Key，可在 conftest 中 mock `app.integrations.embedding_service`，
  或保证环境变量 LLM_API_KEY 可用以跑通自动化。
"""

import io

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient) -> str:
    """注册并登录，返回 Bearer token。"""
    username: str = "tester"
    client.post("/api/v1/auth/register", json={"username": username, "password": "123456"})
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": "123456"})

    assert resp.status_code == 200
    token: str = resp.json()["data"]["access_token"]
    return token


def test_health(client: TestClient) -> None:
    """健康检查无需鉴权。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_register_login_me(client: TestClient) -> None:
    """注册 → 登录 → 获取当前用户。"""
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/auth/me", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["username"] == "tester"


def test_document_upload_and_list(client: TestClient) -> None:
    """上传 TXT → 文档列表应包含该文档。"""
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    content: bytes = "RAG 是检索增强生成的简称，用于结合外部知识库进行问答。".encode("utf-8")
    files: dict[str, tuple[str, io.BytesIO, str]] = {
        "file": ("rag.txt", io.BytesIO(content), "text/plain")
    }

    resp = client.post("/api/v1/documents/upload", headers=headers, files=files)
    assert resp.status_code == 200
    document_id: int = resp.json()["data"]["id"]

    list_resp = client.get("/api/v1/documents", headers=headers)
    assert list_resp.status_code == 200

    items: list[dict] = list_resp.json()["data"]["items"]
    assert any(item["id"] == document_id for item in items)


def test_document_delete(client: TestClient) -> None:
    """删除文档后，列表不再包含该文档。"""
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    content: bytes = "临时文档内容".encode("utf-8")
    files: dict[str, tuple[str, io.BytesIO, str]] = {
        "file": ("temp.txt", io.BytesIO(content), "text/plain")
    }
    document_id: int = client.post("/api/v1/documents/upload", headers=headers, files=files).json()[
        "data"
    ]["id"]

    del_resp = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["id"] == document_id

    list_resp = client.get("/api/v1/documents", headers=headers)
    items: list[dict] = list_resp.json()["data"]["items"]
    assert not any(item["id"] == document_id for item in items)


def test_conversation_flow(client: TestClient) -> None:
    """创建会话 → 列表 → 删除会话。"""
    token: str = _register_and_login(client)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}

    conv_resp = client.post("/api/v1/conversations", headers=headers, json={"title": "测试会话"})
    assert conv_resp.status_code == 200
    conversation_id: int = conv_resp.json()["data"]["id"]

    list_resp = client.get("/api/v1/conversations", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] >= 1

    del_resp = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["id"] == conversation_id
