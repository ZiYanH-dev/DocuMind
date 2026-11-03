"""检索流水线的编排与降级测试（不连数据库、不连模型）。

这是消融实验数据背后的那条链路。各阶段的开关组合必须都能得到确定的
退化结果 —— "关掉重排就退化为混合召回、再关关键词就退化为纯向量"这类
设计意图，此前只写在文档注释里，没有任何用例保证它仍然成立。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.retrieval import pipeline as pipeline_module
from app.retrieval.pipeline import retrieve
from tests.fakes import FakeCache, FakeSession

DEFAULT_CONFIG: dict[str, Any] = {
    "vector_top_k": 4,
    "vector_recall_k": 20,
    "vector_score_threshold": None,
    "keyword_enabled": False,
    "keyword_recall_k": 20,
    "rewrite_enabled": False,
    "rewrite_count": 2,
    "fusion_k": 60,
    "rerank_enabled": False,
}


def _row(chunk_id: int, document_id: int = 1, content: str = "片段", score: float = 0.9) -> dict:
    """构造一条召回结果。"""

    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "document_title": "rag.txt",
        "chunk_index": chunk_id,
        "content": f"{content}{chunk_id}",
        "score": score,
    }


@dataclass
class _StubChunkRepo:
    """ChunkRepository 替身：记录调用，返回预置语料。"""

    rows: list[dict[str, Any]] = field(default_factory=list)
    corpus: list[dict[str, Any]] = field(default_factory=list)
    vector_calls: list[int] = field(default_factory=list)

    def vector_search(
        self,
        user_id: int,
        embedding: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        self.vector_calls.append(user_id)
        return [dict(row) for row in self.rows]

    def list_all_by_user(self, user_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self.corpus]

    def corpus_fingerprint(self, user_id: int) -> str:
        return "stub-fingerprint"


@pytest.fixture()
def configure(monkeypatch: pytest.MonkeyPatch):
    """按开关组合覆盖 pipeline 的配置。"""

    def _apply(**overrides: Any) -> None:
        config = dict(DEFAULT_CONFIG)
        config.update(overrides)
        monkeypatch.setattr(pipeline_module, "settings", SimpleNamespace(**config))

    return _apply


@pytest.fixture()
def chunk_repo(monkeypatch: pytest.MonkeyPatch) -> _StubChunkRepo:
    """替换 ChunkRepository，避免落到真实 pgvector。"""

    stub = _StubChunkRepo()
    monkeypatch.setattr(pipeline_module, "ChunkRepository", lambda session: stub)
    return stub


@pytest.fixture()
def rerank_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, int]]:
    """替换重排模型，只记录调用参数。"""

    calls: list[tuple[str, int, int]] = []

    def _fake_rerank(question: str, candidates: list[Any], top_n: int = 4) -> list[Any]:
        calls.append((question, len(candidates), top_n))
        return candidates[:top_n]

    monkeypatch.setattr(pipeline_module, "rerank", _fake_rerank)
    return calls


@pytest.fixture()
def rewrite_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """替换查询改写（LLM 调用），记录调用参数。"""

    calls: list[tuple[str, int]] = []

    def _fake_rewrite(question: str, count: int) -> list[str]:
        calls.append((question, count))
        return [f"{question} 变体{index}" for index in range(count)]

    monkeypatch.setattr(pipeline_module, "rewrite_queries", _fake_rewrite)
    return calls


@pytest.fixture()
def pipeline_cache(monkeypatch: pytest.MonkeyPatch) -> FakeCache:
    """替换检索缓存，使缓存行为可确定性断言。"""

    stub = FakeCache()
    monkeypatch.setattr(pipeline_module, "cache", stub)
    return stub


# ── 三种链路形态 ──────────────────────────────────────────────


def test_pure_vector_recall_when_other_stages_disabled(
    configure, chunk_repo: _StubChunkRepo, rerank_calls, rewrite_calls
) -> None:
    """全部开关关闭时退化为纯向量检索。"""

    configure()
    chunk_repo.rows = [_row(1), _row(2)]

    results = retrieve(FakeSession(), user_id=7, question="什么是 RAG？", use_cache=False)

    assert [row["recall"] for row in results] == ["vector", "vector"]
    assert rerank_calls == []
    assert rewrite_calls == []
    assert len(chunk_repo.vector_calls) == 1


def test_hybrid_recall_adds_keyword_hits(
    configure, chunk_repo: _StubChunkRepo, rerank_calls
) -> None:
    """开启关键词后，结果里必须出现 keyword 来源的片段。"""

    configure(keyword_enabled=True)
    chunk_repo.rows = [_row(1, content="RAG 向量命中")]
    # 语料必须是 3 条：BM25 的 IDF 为 log((N-df+0.5)/(df+0.5))，
    # 语料过小时（N=df 或 N-df≈df）分数会被压到 0，进而被 `score > 0` 过滤，
    # 表现为"关键词这一路凭空消失"。真实知识库分块数远大于此，不会遇到。
    chunk_repo.corpus = [
        _row(2, content="RAG 关键词命中"),
        _row(3, content="无关内容甲"),
        _row(4, content="无关内容乙"),
    ]

    results = retrieve(FakeSession(), user_id=7, question="RAG", use_cache=False)

    sources = {row["recall"] for row in results}
    assert sources == {"vector", "keyword"}
    assert rerank_calls == []  # 重排仍关闭


def test_rerank_is_applied_after_fusion(
    configure, chunk_repo: _StubChunkRepo, rerank_calls
) -> None:
    """开启重排后，候选先融合再交给重排，并遵守 top_k。"""

    configure(rerank_enabled=True, vector_top_k=2)
    chunk_repo.rows = [_row(1), _row(2), _row(3)]

    results = retrieve(FakeSession(), user_id=7, question="RAG", use_cache=False)

    assert len(results) == 2
    assert rerank_calls == [("RAG", 3, 2)]


def test_rerank_skipped_when_no_candidates(
    configure, chunk_repo: _StubChunkRepo, rerank_calls
) -> None:
    """空语料不去打扰重排模型，直接返回空结果。"""

    configure(rerank_enabled=True)
    chunk_repo.rows = []

    assert retrieve(FakeSession(), user_id=7, question="RAG", use_cache=False) == []
    assert rerank_calls == []


def test_rewrite_produces_one_recall_per_query_variant(
    configure, chunk_repo: _StubChunkRepo, rewrite_calls
) -> None:
    """开启查询改写后，每个变体都各自召回一次。"""

    configure(rewrite_enabled=True, rewrite_count=2)
    chunk_repo.rows = [_row(1)]

    retrieve(FakeSession(), user_id=7, question="RAG", use_cache=False)

    assert rewrite_calls == [("RAG", 2)]
    assert len(chunk_repo.vector_calls) == 3  # 原问题 + 2 个变体


# ── top_k 与租户 ──────────────────────────────────────────────


def test_top_k_overrides_settings(configure, chunk_repo: _StubChunkRepo) -> None:
    """显式传入 top_k 优先于配置值。"""

    configure(vector_top_k=4)
    chunk_repo.rows = [_row(index) for index in range(1, 6)]

    results = retrieve(FakeSession(), user_id=7, question="RAG", top_k=1, use_cache=False)

    assert len(results) == 1


def test_retrieval_is_scoped_to_user(configure, chunk_repo: _StubChunkRepo) -> None:
    """检索必须带上用户 ID，否则会读别人的知识库。"""

    configure()

    retrieve(FakeSession(), user_id=42, question="RAG", use_cache=False)

    assert chunk_repo.vector_calls == [42]


# ── 缓存 ──────────────────────────────────────────────────────


def test_cache_hit_skips_retrieval(
    configure, chunk_repo: _StubChunkRepo, pipeline_cache: FakeCache
) -> None:
    """命中缓存时不再查询数据库。"""

    configure()
    chunk_repo.rows = [_row(1)]
    pipeline_cache.data[pipeline_module.retrieval_key(7, "RAG")] = [_row(9)]

    results = retrieve(FakeSession(), user_id=7, question="RAG")

    assert [row["chunk_id"] for row in results] == [9]
    assert chunk_repo.vector_calls == []


def test_result_is_written_back_to_cache(
    configure, chunk_repo: _StubChunkRepo, pipeline_cache: FakeCache
) -> None:
    """未命中时把结果写回缓存，供下一轮复用。"""

    configure()
    chunk_repo.rows = [_row(1)]

    retrieve(FakeSession(), user_id=7, question="RAG")

    key = pipeline_module.retrieval_key(7, "RAG")
    assert [row["chunk_id"] for row in pipeline_cache.data[key]] == [1]


def test_use_cache_false_skips_cache_entirely(
    configure, chunk_repo: _StubChunkRepo, pipeline_cache: FakeCache
) -> None:
    """评估脚本传 use_cache=False 时不读也不写，保证测出真实耗时。"""

    configure()
    chunk_repo.rows = [_row(1)]
    pipeline_cache.data[pipeline_module.retrieval_key(7, "RAG")] = [_row(9)]

    results = retrieve(FakeSession(), user_id=7, question="RAG", use_cache=False)

    assert [row["chunk_id"] for row in results] == [1]
    assert pipeline_cache.set_calls == []


def test_cache_is_keyed_by_user(
    configure, chunk_repo: _StubChunkRepo, pipeline_cache: FakeCache
) -> None:
    """不同用户的同一问题不能共用缓存。"""

    configure()
    chunk_repo.rows = [_row(1)]

    retrieve(FakeSession(), user_id=1, question="RAG")
    retrieve(FakeSession(), user_id=2, question="RAG")

    assert len(pipeline_cache.data) == 2
