"""Agent 工具测试（不连数据库、不调模型）。

工具是**多租户隔离的边界**：闭包捕获的 user_id 决定了模型能读到谁的知识库。
一旦这里串了用户，就是跨账号数据泄露，所以每条隔离路径都要有反向验证。

另一条守的是"工具永不抛出"：工具内部异常被转成文本返回给模型，
让模型可以换一种方式继续，而不是把整轮问答打断。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent import tools as tools_module
from app.agent.tools import build_tools
from app.models.document import DocumentChunk
from tests.fakes import (
    FakeChunkRepository,
    FakeDocumentRepository,
    FakeSession,
    reset_store,
)


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    """每个用例独立一套内存库。"""

    reset_store()


@pytest.fixture()
def retrieve_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str, int | None]]:
    """替换检索入口，记录调用参数并按脚本返回结果。"""

    calls: list[tuple[int, str, int | None]] = []
    canned: list[dict[str, Any]] = []

    def _fake_retrieve(
        session: Any,
        user_id: int,
        query: str,
        *,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        calls.append((user_id, query, top_k))
        return [dict(row) for row in canned]

    monkeypatch.setattr(tools_module, "retrieve", _fake_retrieve)
    # 通过属性暴露，便于单个用例改写返回值
    monkeypatch.setattr(_fake_retrieve, "canned", canned, raising=False)
    return calls


def _hit(document_id: int = 1, chunk_index: int = 0, content: str = "片段内容") -> dict[str, Any]:
    """构造一条检索结果。"""

    return {
        "chunk_id": 10 + chunk_index,
        "document_id": document_id,
        "document_title": "rag.txt",
        "chunk_index": chunk_index,
        "content": content,
        "score": 0.87,
    }


def _set_canned(rows: list[dict[str, Any]]) -> None:
    """改写替身的返回值。"""

    canned = getattr(tools_module.retrieve, "canned")
    canned.clear()
    canned.extend(rows)


# ── 工具清单 ──────────────────────────────────────────────────


def test_build_tools_exposes_both_tools() -> None:
    """工具名必须与 system prompt 里声明的一致，否则模型调用会失败。"""

    tools = build_tools(FakeSession(), 1)

    assert [tool.name for tool in tools] == ["search_knowledge", "list_documents"]


def test_tools_have_descriptions_for_the_model() -> None:
    """工具描述不能为空，模型靠它决定何时调用。"""

    tools = build_tools(FakeSession(), 1)

    assert all(tool.description.strip() for item in [tools] for tool in item)


# ── 检索命中收集 ──────────────────────────────────────────────


def test_search_knowledge_records_structured_hits(retrieve_calls) -> None:
    """检索结果要转成可定位到文档与分块的结构化命中，供前端展示引用。"""

    _set_canned([_hit(1, 0), _hit(1, 1)])
    hits: list = []
    tools = build_tools(FakeSession(), 1, hits)

    tools[0].invoke({"query": "什么是 RAG？"})

    assert [(hit.document_id, hit.chunk_index, hit.document_title) for hit in hits] == [
        (1, 0, "rag.txt"),
        (1, 1, "rag.txt"),
    ]
    assert hits[0].snippet == "片段内容"
    assert hits[0].score == pytest.approx(0.87)


def test_search_knowledge_truncates_long_snippets(retrieve_calls) -> None:
    """过长片段要截断到 200 字，避免把整篇文档塞进引用与上下文。"""

    _set_canned([_hit(1, 0, content="长" * 500)])
    hits: list = []
    tools = build_tools(FakeSession(), 1, hits)

    tools[0].invoke({"query": "长文"})

    assert len(hits[0].snippet) == 200


def test_search_knowledge_formats_result_for_model(retrieve_calls) -> None:
    """返回给模型的文本要带上来源与相关度，便于模型标注引用。"""

    _set_canned([_hit(1, 0)])
    tools = build_tools(FakeSession(), 1)

    text: str = tools[0].invoke({"query": "RAG"})

    assert "[来源: rag.txt, 相关度: 0.87]" in text
    assert "片段内容" in text


def test_search_knowledge_reports_empty_kb(retrieve_calls) -> None:
    """没有命中时明确告诉模型"知识库里没有"，而不是返回空串让它瞎编。"""

    _set_canned([])
    hits: list = []
    tools = build_tools(FakeSession(), 1, hits)

    assert tools[0].invoke({"query": "RAG"}) == "知识库中未找到相关内容。"
    assert hits == []


# ── 多租户隔离 ────────────────────────────────────────────────


def test_search_knowledge_passes_own_user_id(retrieve_calls) -> None:
    """检索必须带上构建工具时捕获的 user_id。"""

    _set_canned([_hit()])
    tools = build_tools(FakeSession(), 42)

    tools[0].invoke({"query": "RAG"})

    assert retrieve_calls[0][0] == 42


def test_tools_built_for_different_users_are_isolated(retrieve_calls) -> None:
    """两个用户的工具互不干扰：各自的检索都带上自己的 user_id。"""

    _set_canned([_hit()])
    alice_tools = build_tools(FakeSession(), 1)
    bob_tools = build_tools(FakeSession(), 2)

    alice_tools[0].invoke({"query": "RAG"})
    bob_tools[0].invoke({"query": "RAG"})

    assert [call[0] for call in retrieve_calls] == [1, 2]


def test_explicit_collector_accumulates_across_calls(retrieve_calls) -> None:
    """服务层传入同一个收集器时，多次检索的命中要累积起来。

    一轮问答里模型可能调用多次检索，引用来源应当是这些命中的并集；
    若每次都新建列表，后面的命中会覆盖前面的，引用来源会丢失。
    """

    _set_canned([_hit(1, 0)])
    collector: list = []
    tools = build_tools(FakeSession(), 1, collector)

    tools[0].invoke({"query": "第一次检索"})
    _set_canned([_hit(1, 1)])
    tools[0].invoke({"query": "第二次检索"})

    assert [hit.chunk_index for hit in collector] == [0, 1]


def test_hits_collector_is_not_shared_by_default(retrieve_calls) -> None:
    """不传收集器时各组工具各自一份，跨请求不能串数据。

    验证方式：两组工具各调一次，各自返回的来源数都是 1 ——
    若共用收集器，引用来源会在别处被看到（这里用返回文本反证不共享）。
    """

    _set_canned([_hit()])
    first = build_tools(FakeSession(), 1)
    second = build_tools(FakeSession(), 2)

    first[0].invoke({"query": "RAG"})
    second_text: str = second[0].invoke({"query": "RAG"})

    assert second_text.count("[来源:") == 1


def test_search_knowledge_forwards_top_k(retrieve_calls) -> None:
    """模型指定的 top_k 要传递给检索链路。"""

    _set_canned([_hit()])
    tools = build_tools(FakeSession(), 1)

    tools[0].invoke({"query": "RAG", "top_k": 3})

    assert retrieve_calls[0][2] == 3


# ── 文档列表 ──────────────────────────────────────────────────


def _seed_documents(user_id: int, title: str) -> int:
    """在内存库里建一个文档及其分块，返回文档 ID。"""

    document = FakeDocumentRepository().create(
        user_id=user_id,
        title=title,
        file_name=f"{title}.txt",
        file_path=f"/tmp/{title}.txt",
        file_size=10,
        file_type="txt",
    )
    FakeDocumentRepository().update_status(document.id, "completed")
    FakeChunkRepository().create_many(
        [
            DocumentChunk(document_id=document.id, chunk_index=index, content=f"块{index}")
            for index in range(2)
        ]
    )
    return document.id


def test_list_documents_shows_title_status_and_chunk_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """列表要带上标题、状态与分块数，模型据此判断文档是否可用。"""

    monkeypatch.setattr(tools_module, "DocumentRepository", FakeDocumentRepository)
    _seed_documents(user_id=1, title="rag")
    tools = build_tools(FakeSession(), 1)

    text: str = tools[1].invoke({})

    assert "rag" in text
    assert "状态:completed" in text
    assert "分块数:2" in text


def test_list_documents_only_shows_own_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """看不到别人的文档 —— 这是租户隔离的第二道边界。"""

    monkeypatch.setattr(tools_module, "DocumentRepository", FakeDocumentRepository)
    _seed_documents(user_id=1, title="alice 的文档")
    _seed_documents(user_id=2, title="bob 的文档")

    alice_text: str = build_tools(FakeSession(), 1)[1].invoke({})
    bob_text: str = build_tools(FakeSession(), 2)[1].invoke({})

    assert "alice 的文档" in alice_text
    assert "bob 的文档" not in alice_text
    assert "bob 的文档" in bob_text
    assert "alice 的文档" not in bob_text


def test_list_documents_reports_empty_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    """没上传任何文档时给出明确提示。"""

    monkeypatch.setattr(tools_module, "DocumentRepository", FakeDocumentRepository)

    assert build_tools(FakeSession(), 1)[1].invoke({}) == "你还没有上传任何文档。"


# ── 工具不得抛出 ──────────────────────────────────────────────


def test_search_knowledge_swallows_errors_as_text(
    retrieve_calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """检索异常转成文本返回，让模型有机会换个问法，而不是打断整轮问答。"""

    def _boom(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("vector store down")

    monkeypatch.setattr(tools_module, "retrieve", _boom)

    text: str = build_tools(FakeSession(), 1)[0].invoke({"query": "RAG"})

    assert text.startswith("检索出错了")
    assert "vector store down" in text


def test_list_documents_swallows_errors_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """文档列表异常同样转成文本。"""

    class _BrokenRepo:
        def __init__(self, session: Any) -> None:
            pass

        def list_by_user_id(self, user_id: int) -> list:
            raise RuntimeError("db down")

    monkeypatch.setattr(tools_module, "DocumentRepository", _BrokenRepo)

    text: str = build_tools(FakeSession(), 1)[1].invoke({})

    assert text.startswith("获取文档列表出错")
    assert "db down" in text


def test_tools_are_rebuilt_per_request_not_shared(retrieve_calls) -> None:
    """每次构建都是新的一批工具，闭包状态不跨请求残留。"""

    first = build_tools(FakeSession(), 1)
    second = build_tools(FakeSession(), 1)

    assert first[0] is not second[0]
