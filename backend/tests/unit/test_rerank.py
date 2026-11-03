"""重排单元测试。

重排是外部 HTTP 调用，属于「增强项」：成功则重排，失败则原样返回融合顺序。
这里用假的 httpx.post 覆盖成功、失败、脏数据三条路径。
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.retrieval import rerank as rerank_module
from app.retrieval.rerank import _MAX_CANDIDATES, rerank


class _FakeResponse:
    """最小的 httpx.Response 替身。"""

    def __init__(self, body: Any, raise_error: Exception | None = None) -> None:
        self._body: Any = body
        self._error: Exception | None = raise_error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> Any:
        return self._body


@pytest.fixture()
def _stub_post(monkeypatch: pytest.MonkeyPatch):
    """替换 httpx.post，并记录最后一次请求体。"""

    captured: list[dict[str, Any]] = []

    def _install(response: _FakeResponse) -> None:
        def _post(url: str, **kwargs: Any) -> _FakeResponse:
            captured.append({"url": url, **kwargs})
            return response

        monkeypatch.setattr(rerank_module.httpx, "post", _post)

    return _install, captured


def _candidates(count: int) -> list[dict[str, object]]:
    """构造候选片段，content 互不相同的长文本。"""

    return [
        {"document_id": 1, "chunk_index": i, "content": f"片段{i}的内容", "score": 0.9 - i * 0.1}
        for i in range(count)
    ]


# ── 短路路径 ──────────────────────────────────────────────────


def test_empty_candidates_returns_empty(_stub_post) -> None:
    """没有候选时直接返回，不发无谓的 HTTP 请求。"""

    install, captured = _stub_post
    install(_FakeResponse({"output": {"results": []}}))

    assert rerank("q", []) == []
    assert captured == []


# ── 成功路径 ──────────────────────────────────────────────────


def test_success_reorders_by_returned_index(_stub_post) -> None:
    """按接口返回的 index 顺序重排，score 换成重排分。"""

    install, _ = _stub_post
    install(
        _FakeResponse(
            {
                "output": {
                    "results": [
                        {"index": 2, "relevance_score": 0.95},
                        {"index": 0, "relevance_score": 0.40},
                    ]
                }
            }
        )
    )

    results = rerank("q", _candidates(3))

    assert [int(r["chunk_index"]) for r in results] == [2, 0]
    assert float(results[0]["score"]) == 0.95
    assert float(results[0]["rerank_score"]) == 0.95


def test_recall_is_tagged_with_rerank(_stub_post) -> None:
    """recall 追加 rerank 标记，便于在链路日志里区分经过重排的片段。"""

    install, _ = _stub_post
    install(_FakeResponse({"output": {"results": [{"index": 0, "relevance_score": 0.9}]}}))

    results = rerank("q", [{"chunk_index": 0, "content": "内容", "recall": "vector"}])

    assert results[0]["recall"] == "vector+rerank"


def test_recall_without_origin_has_no_leading_separator(_stub_post) -> None:
    """原本没有 recall 时不应出现 '+rerank' 这种前导分隔符。"""

    install, _ = _stub_post
    install(_FakeResponse({"output": {"results": [{"index": 0, "relevance_score": 0.9}]}}))

    results = rerank("q", [{"chunk_index": 0, "content": "内容"}])

    assert results[0]["recall"] == "rerank"


def test_original_fields_are_preserved(_stub_post) -> None:
    """重排只改 score，其余字段原样保留，前端才能继续定位来源。"""

    install, _ = _stub_post
    install(_FakeResponse({"output": {"results": [{"index": 0, "relevance_score": 0.9}]}}))

    results = rerank("q", [{"document_id": 7, "chunk_index": 3, "content": "内容"}])

    assert results[0]["document_id"] == 7
    assert results[0]["chunk_index"] == 3


def test_candidates_are_capped(_stub_post) -> None:
    """候选数超过上限时截断，控制 token 消耗。"""

    install, captured = _stub_post
    install(_FakeResponse({"output": {"results": []}}))

    rerank("q", _candidates(_MAX_CANDIDATES + 5))

    assert len(captured[0]["json"]["input"]["documents"]) == _MAX_CANDIDATES


def test_top_n_is_clamped_to_document_count(_stub_post) -> None:
    """top_n 不应超过实际送入的文档数。"""

    install, captured = _stub_post
    install(_FakeResponse({"output": {"results": []}}))

    rerank("q", _candidates(2), top_n=99)

    assert captured[0]["json"]["parameters"]["top_n"] == 2


def test_timeout_is_always_set(_stub_post) -> None:
    """重排是同步阻塞调用，必须带超时，否则会拖垮整轮检索。"""

    install, captured = _stub_post
    install(_FakeResponse({"output": {"results": []}}))

    rerank("q", _candidates(1))

    assert captured[0]["timeout"] > 0


# ── 降级路径 ──────────────────────────────────────────────────


def test_http_error_falls_back_to_fused_order(_stub_post) -> None:
    """接口报错时原样返回融合顺序，不中断检索。"""

    install, _ = _stub_post
    install(_FakeResponse(None, raise_error=httpx.HTTPError("502")))

    candidates: list[dict[str, object]] = _candidates(3)

    assert rerank("q", candidates, top_n=2) == candidates[:2]


def test_invalid_json_falls_back(_stub_post) -> None:
    """响应体不是合法 JSON 时降级。"""

    install, _ = _stub_post
    install(_FakeResponse(None, raise_error=ValueError("not json")))

    candidates: list[dict[str, object]] = _candidates(3)

    assert rerank("q", candidates, top_n=2) == candidates[:2]


def test_missing_results_falls_back(_stub_post) -> None:
    """响应里没有 results 字段时降级。"""

    install, _ = _stub_post
    install(_FakeResponse({"output": {}}))

    candidates: list[dict[str, object]] = _candidates(3)

    assert rerank("q", candidates, top_n=2) == candidates[:2]


def test_out_of_range_index_is_skipped(_stub_post) -> None:
    """越界 index 被跳过，防止 IndexError 打断整轮检索。"""

    install, _ = _stub_post
    install(
        _FakeResponse(
            {
                "output": {
                    "results": [
                        {"index": 99, "relevance_score": 0.9},
                        {"index": 0, "relevance_score": 0.5},
                    ]
                }
            }
        )
    )

    results = rerank("q", _candidates(2))

    assert [int(r["chunk_index"]) for r in results] == [0]


def test_all_results_invalid_falls_back(_stub_post) -> None:
    """全部结果都无效时降级为融合顺序，而不是返回空列表丢掉召回结果。"""

    install, _ = _stub_post
    install(_FakeResponse({"output": {"results": [{"index": 99, "relevance_score": 0.9}]}}))

    candidates: list[dict[str, object]] = _candidates(2)

    assert rerank("q", candidates, top_n=2) == candidates[:2]
