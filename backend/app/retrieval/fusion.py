"""召回结果融合 —— 倒数排名融合。

多路召回各自返回一个按相关度排序的列表，两路的分数尺度不同，不能直接相加。
倒数排名融合只看名次不看分数，因此对异构召回器天然适用。
"""

from __future__ import annotations


def _key_of(item: dict[str, object]) -> tuple[int, int]:
    """片段的稳定标识，同一片段在不同路里要能对上。"""

    return int(item["document_id"]), int(item["chunk_index"])


def rrf_fuse(
    rankings: list[list[dict[str, object]]],
    *,
    k: int = 60,
    top_k: int | None = None,
) -> list[dict[str, object]]:
    """把多路召回结果融合成一个按相关度降序的列表。

    每一路里第 rank 名贡献 1 / (k + rank) 分，同一片段在多路中出现则分数累加，
    因此被两路同时召回的片段会排到前面。返回结果里 score 是归一化到 0 到 1 的
    融合分，rrf_score 是原始融合分，recall 记录该片段被哪几路召回。
    """

    scores: dict[tuple[int, int], float] = {}
    payload: dict[tuple[int, int], dict[str, object]] = {}
    sources: dict[tuple[int, int], list[str]] = {}

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            key = _key_of(item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            payload.setdefault(key, item)
            source = str(item.get("recall", ""))
            if source:
                bucket = sources.setdefault(key, [])
                if source not in bucket:
                    bucket.append(source)

    if not scores:
        return []

    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    if top_k is not None:
        ordered = ordered[:top_k]

    best = ordered[0][1]
    fused: list[dict[str, object]] = []
    for key, score in ordered:
        item = dict(payload[key])
        item["score"] = round(score / best, 6) if best else 0.0
        item["rrf_score"] = round(score, 6)
        item["recall"] = "+".join(sources.get(key, []))
        fused.append(item)
    return fused
