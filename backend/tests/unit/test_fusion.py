"""倒数排名融合（RRF）单元测试。

融合层是纯函数，不碰数据库与网络，因此可以全量覆盖边界行为。
它决定了「被多路同时召回的片段能否排到前面」，直接关系检索质量。
"""

from __future__ import annotations

import pytest

from app.retrieval.fusion import rrf_fuse


def _hit(document_id: int, chunk_index: int, recall: str) -> dict[str, object]:
    """构造一条召回结果。"""

    return {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": f"doc{document_id}-chunk{chunk_index}",
        "score": 0.5,
        "recall": recall,
    }


def test_empty_rankings_return_empty() -> None:
    """没有任何召回结果时返回空列表，不抛异常。"""

    assert rrf_fuse([]) == []
    assert rrf_fuse([[], []]) == []


def test_single_ranking_preserves_order() -> None:
    """单路召回时，融合结果保持原有名次顺序。"""

    ranking: list[dict[str, object]] = [_hit(1, 0, "vector"), _hit(1, 1, "vector")]
    fused = rrf_fuse([ranking])

    assert [(item["document_id"], item["chunk_index"]) for item in fused] == [(1, 0), (1, 1)]


def test_top_score_is_normalized_to_one() -> None:
    """第一名归一化后 score 为 1.0，便于跨查询比较相关度。"""

    fused = rrf_fuse([[_hit(1, 0, "vector"), _hit(1, 1, "vector")]])

    assert fused[0]["score"] == 1.0
    assert 0.0 < float(fused[1]["score"]) < 1.0


def test_item_hit_by_both_recallers_ranks_first() -> None:
    """同一片段被两路召回时分数累加，应当排到只被单路召回的片段之前。"""

    vector_rank: list[dict[str, object]] = [_hit(1, 0, "vector"), _hit(2, 0, "vector")]
    keyword_rank: list[dict[str, object]] = [_hit(2, 0, "keyword"), _hit(3, 0, "keyword")]

    fused = rrf_fuse([vector_rank, keyword_rank])

    # 2 号片段在两路里都出现，分数叠加后应超越只在第一路排第一的 1 号
    assert fused[0]["document_id"] == 2
    assert fused[0]["recall"] == "vector+keyword"


def test_recall_field_joins_all_sources() -> None:
    """recall 字段记录该片段被哪几路召回，用于链路排查。"""

    fused = rrf_fuse([[_hit(1, 0, "vector")], [_hit(1, 0, "keyword")]])

    assert fused[0]["recall"] == "vector+keyword"


def test_top_k_truncates_result() -> None:
    """top_k 生效时只保留前若干条。"""

    ranking: list[dict[str, object]] = [_hit(1, i, "vector") for i in range(5)]
    fused = rrf_fuse([ranking], top_k=2)

    assert len(fused) == 2


def test_k_parameter_changes_score_scale() -> None:
    """k 越大，名次带来的分数差距越小（衰减越平缓）。"""

    ranking: list[dict[str, object]] = [_hit(1, 0, "vector"), _hit(1, 1, "vector")]

    small_k = rrf_fuse([ranking], k=1)
    large_k = rrf_fuse([ranking], k=1000)

    # k=1 时第二名得分 1/3，k=1000 时约 1/1002，差距被压缩
    assert float(small_k[1]["rrf_score"]) > float(large_k[1]["rrf_score"])


def test_duplicate_item_uses_first_payload() -> None:
    """同一片段在多路中出现时，内容取首次出现的那条，后续路不覆盖正文。"""

    first: dict[str, object] = {**_hit(1, 0, "vector"), "content": "首次内容"}
    second: dict[str, object] = {**_hit(1, 0, "keyword"), "content": "后来内容"}

    fused = rrf_fuse([[first], [second]])

    assert fused[0]["content"] == "首次内容"


@pytest.mark.parametrize("missing_field", ["document_id", "chunk_index"])
def test_missing_identity_field_raises(missing_field: str) -> None:
    """缺少定位字段时应当报错，而不是静默产生无法溯源的结果。"""

    broken: dict[str, object] = _hit(1, 0, "vector")
    del broken[missing_field]

    with pytest.raises(KeyError):
        rrf_fuse([[broken]])
