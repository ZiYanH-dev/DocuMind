"""结果重排 —— 调用百炼原生重排接口。

融合后的分数是按名次合成的，粒度较粗。重排模型直接对「查询与片段」这一对文本
打分，能把真正切题的片段提到前面。

百炼的重排接口不在 OpenAI 兼容协议内，因此这里直接发 HTTP 请求，
复用 LLM 的 API Key，不引入额外依赖。重排失败时原样返回融合顺序，不影响主链路。
"""

from __future__ import annotations

import logging

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# 重排是同步阻塞调用，超时直接放弃重排，不拖垮整轮检索
_TIMEOUT_SECONDS = 20.0
# 单次请求最多送入的候选数，控制 token 消耗
_MAX_CANDIDATES = 30


def rerank(
    query: str,
    candidates: list[dict[str, object]],
    *,
    top_n: int | None = None,
    model: str | None = None,
) -> list[dict[str, object]]:
    """按相关度重排候选片段。

    返回结果保持与输入相同的字典结构，score 替换为重排相关度，
    另留 rerank_score 字段供排查问题。
    """

    if not candidates:
        return []

    limit = top_n or settings.rerank_top_n
    model_name = model or settings.rerank_model

    documents = [str(item["content"]) for item in candidates[:_MAX_CANDIDATES]]
    payload = {
        "model": model_name,
        "input": {"query": query, "documents": documents},
        "parameters": {"top_n": min(limit, len(documents))},
    }

    try:
        response = httpx.post(
            settings.rerank_endpoint,
            headers={
                "Authorization": f"Bearer {settings.effective_rerank_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("rerank request failed, keep fused order: %s", exc)
        return candidates[:limit]

    results = body.get("output", {}).get("results")
    if not isinstance(results, list) or not results:
        logger.warning("rerank returned no result, keep fused order")
        return candidates[:limit]

    reranked: list[dict[str, object]] = []
    for entry in results:
        index = entry.get("index")
        if not isinstance(index, int) or not 0 <= index < len(documents):
            continue
        item = dict(candidates[index])
        score = float(entry.get("relevance_score", 0.0))
        item["rerank_score"] = score
        item["score"] = score
        origin = str(item.get("recall", ""))
        item["recall"] = f"{origin}+rerank" if origin else "rerank"
        reranked.append(item)

    return reranked or candidates[:limit]
