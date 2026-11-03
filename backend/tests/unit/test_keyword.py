"""BM25 关键词召回单元测试。

KeywordRetriever 的语料读取由调用方注入（``load_fingerprint`` / ``load_chunks``），
因此这里可以完全脱离数据库测试索引构建、缓存与失效逻辑。
"""

from __future__ import annotations

import pytest

from app.retrieval import keyword as keyword_module
from app.retrieval.keyword import (
    EMPTY_FINGERPRINT,
    KeywordRetriever,
    invalidate,
    invalidate_all,
    tokenize,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    """每个用例前后清空进程内索引缓存，避免用例之间互相污染。"""

    invalidate_all()
    yield
    invalidate_all()


def _chunk(document_id: int, chunk_index: int, content: str) -> dict[str, object]:
    """构造一条语料片段。"""

    return {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": content,
    }


def _retriever(chunks: list[dict[str, object]], fingerprint: str = "fp-1") -> KeywordRetriever:
    """用固定的语料构造召回器。"""

    return KeywordRetriever(
        load_fingerprint=lambda user_id: fingerprint,
        load_chunks=lambda user_id: chunks,
    )


def _corpus_with_unique_term(total: int = 4) -> list[dict[str, object]]:
    """构造语料：仅第一条含目标术语，其余为无关内容。

    BM25 的 idf 为 ``log(N - df + 0.5) - log(df + 0.5)``，当 ``df >= N / 2``
    时会退化到 0 甚至为负，此时分数为 0，会被 ``score > 0`` 过滤掉，
    关键词这一路等于整路失效。因此测试语料至少需要 3 条以上。
    """

    chunks: list[dict[str, object]] = [_chunk(1, 0, "线程是 CPU 调度的基本单位")]
    for index in range(1, total):
        chunks.append(_chunk(2, index, f"数据库连接池的第 {index} 种配置项说明"))
    return chunks


# ── 分词 ──────────────────────────────────────────────────────


def test_tokenize_drops_whitespace_and_punctuation() -> None:
    """jieba 会切出空格与标点，必须过滤掉，否则会污染 BM25 词表。"""

    tokens: list[str] = tokenize("线程 是 CPU 调度的基本单位，。")

    assert "" not in tokens
    assert " " not in tokens
    assert "线程" in tokens


def test_tokenize_lowercases_english() -> None:
    """英文统一转小写，保证大小写不敏感。"""

    assert "rag" in tokenize("RAG")


def test_tokenize_empty_text_returns_empty() -> None:
    """空文本切不出词。"""

    assert tokenize("") == []


# ── 召回行为 ──────────────────────────────────────────────────


def test_empty_corpus_returns_no_hit() -> None:
    """语料为空时直接返回空，不尝试建索引。"""

    retriever = _retriever([], fingerprint=EMPTY_FINGERPRINT)

    assert retriever.search(1, "线程", top_k=5) == []


def test_query_without_terms_returns_no_hit() -> None:
    """查询切不出词时不召回，避免返回全量语料。"""

    retriever = _retriever([_chunk(1, 0, "线程是调度单位")])

    assert retriever.search(1, "，。 ", top_k=5) == []


def test_relevant_chunk_is_retrieved() -> None:
    """命中术语的片段应当被召回，且带 recall=keyword 标记。"""

    results = _retriever(_corpus_with_unique_term()).search(1, "线程", top_k=5)

    assert results
    assert results[0]["document_id"] == 1
    assert results[0]["recall"] == "keyword"
    assert float(results[0]["score"]) > 0


def test_zero_score_chunks_are_filtered() -> None:
    """与查询无任何词重合的片段分数为 0，不应进入召回结果。"""

    results = _retriever(_corpus_with_unique_term()).search(1, "线程", top_k=5)

    document_ids: list[int] = [int(item["document_id"]) for item in results]
    assert 2 not in document_ids


def test_top_k_limits_result_size() -> None:
    """top_k 控制召回条数。"""

    chunks: list[dict[str, object]] = [_chunk(1, i, f"线程的第 {i} 种说法") for i in range(5)]

    assert len(_retriever(chunks).search(1, "线程", top_k=2)) <= 2


def test_original_chunk_fields_are_preserved() -> None:
    """召回结果保留原始字段，融合层才能按 document_id + chunk_index 对齐。"""

    chunks: list[dict[str, object]] = _corpus_with_unique_term()
    chunks[0] = _chunk(7, 3, "线程是 CPU 调度的基本单位")

    results = _retriever(chunks).search(1, "线程", top_k=5)

    assert results[0]["document_id"] == 7
    assert results[0]["chunk_index"] == 3
    assert results[0]["content"] == "线程是 CPU 调度的基本单位"


def test_small_corpus_makes_keyword_recall_silent() -> None:
    """已知边界：语料太少时 idf 退化为 0，关键词这一路会整路空手而归。

    语料 2 条、目标词出现在其中 1 条时，idf = log(2-1+0.5) - log(1+0.5) = 0，
    分数为 0 被过滤。这不是缺陷而是 BM25 的性质，但它意味着「用户只上传了一两
    个文档时，混合召回实际退化为纯向量召回」。这里固化该行为，便于日后据此决定
    是否要为小语料加兜底。
    """

    two_chunks: list[dict[str, object]] = [
        _chunk(1, 0, "线程是 CPU 调度的基本单位"),
        _chunk(2, 0, "数据库连接池的配置方法"),
    ]

    assert _retriever(two_chunks).search(1, "线程", top_k=5) == []


# ── 缓存与失效 ────────────────────────────────────────────────


def test_index_is_rebuilt_when_fingerprint_changes() -> None:
    """语料指纹变化后必须重建索引，否则上传新文档后检索不到。"""

    calls: list[int] = []

    def _load_chunks(user_id: int) -> list[dict[str, object]]:
        calls.append(user_id)
        return [_chunk(1, 0, "线程调度")]

    retriever = KeywordRetriever(
        load_fingerprint=lambda user_id: f"fp-{len(calls)}",
        load_chunks=_load_chunks,
    )

    retriever.search(1, "线程", top_k=5)
    retriever.search(1, "线程", top_k=5)  # 指纹又变了 → 再次取语料

    assert len(calls) == 2


def test_index_is_reused_when_fingerprint_stable() -> None:
    """指纹不变时复用缓存索引，避免每次检索都全量取语料。"""

    calls: list[int] = []

    def _load_chunks(user_id: int) -> list[dict[str, object]]:
        calls.append(user_id)
        return [_chunk(1, 0, "线程调度")]

    retriever = KeywordRetriever(
        load_fingerprint=lambda user_id: "fp-stable",
        load_chunks=_load_chunks,
    )

    retriever.search(1, "线程", top_k=5)
    retriever.search(1, "线程", top_k=5)

    assert len(calls) == 1


def test_invalidate_forces_rebuild() -> None:
    """文档增删后调用 invalidate，下一次检索必须重新取语料。"""

    calls: list[int] = []
    retriever = KeywordRetriever(
        load_fingerprint=lambda user_id: "fp-stable",
        load_chunks=lambda user_id: calls.append(user_id) or [_chunk(1, 0, "线程调度")],
    )

    retriever.search(1, "线程", top_k=5)
    invalidate(1)
    retriever.search(1, "线程", top_k=5)

    assert len(calls) == 2


def test_cache_is_isolated_per_user() -> None:
    """索引缓存按用户隔离，A 的语料不会出现在 B 的召回结果里。"""

    def _load_chunks(user_id: int) -> list[dict[str, object]]:
        if user_id == 1:
            return _corpus_with_unique_term()
        # 用户 2 的语料里完全没有「线程」
        return [_chunk(2, index, f"数据库连接池的第 {index} 种配置") for index in range(4)]

    retriever = KeywordRetriever(
        load_fingerprint=lambda user_id: f"fp-{user_id}",
        load_chunks=_load_chunks,
    )

    user1_hits = retriever.search(1, "线程", top_k=5)
    user2_hits = retriever.search(2, "线程", top_k=5)

    assert [int(h["document_id"]) for h in user1_hits] == [1]
    assert user2_hits == []


def test_invalidate_all_clears_every_user() -> None:
    """invalidate_all 清空全部用户缓存。"""

    _retriever([_chunk(1, 0, "线程调度")]).search(1, "线程", top_k=5)
    invalidate_all()

    assert keyword_module._cache == {}


def test_corpus_that_tokenizes_to_nothing_is_skipped() -> None:
    """语料全切不出词时 BM25 无法建立，应放弃这一路而不是抛异常。"""

    retriever = _retriever([_chunk(1, 0, "，，。")])

    assert retriever.search(1, "线程", top_k=5) == []
