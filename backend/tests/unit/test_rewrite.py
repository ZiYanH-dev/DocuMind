"""查询改写单元测试。

改写属于「增强项」：它只扩大召回面，失败时必须降级为单查询而不是中断整轮问答。
因此这里既测解析逻辑，也测各类降级路径。
"""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableLambda

from app.retrieval import rewrite as rewrite_module
from app.retrieval.rewrite import _parse_queries, rewrite_queries

# ── 输出解析 ──────────────────────────────────────────────────


def test_parses_plain_json_array() -> None:
    """标准 JSON 数组能解析出来。"""

    assert _parse_queries('["a", "b"]') == ["a", "b"]


def test_strips_markdown_code_fence() -> None:
    """模型常用代码块包裹 JSON，必须剥掉围栏再解析。"""

    assert _parse_queries('```json\n["a", "b"]\n```') == ["a", "b"]
    assert _parse_queries('```\n["a"]\n```') == ["a"]


def test_non_json_returns_empty() -> None:
    """输出不是 JSON 时返回空列表，由调用方降级。"""

    assert _parse_queries("我不是 JSON") == []


def test_non_array_json_returns_empty() -> None:
    """JSON 不是数组时返回空列表。"""

    assert _parse_queries('{"query": "a"}') == []


def test_filters_non_string_items() -> None:
    """数组里的非字符串项被剔除，避免后续 f-string 拼出 'None'。"""

    assert _parse_queries('["a", 123, null, "b"]') == ["a", "b"]


def test_drops_blank_items() -> None:
    """空白项被剔除。"""

    assert _parse_queries('["a", "   ", "b"]') == ["a", "b"]


# ── 降级路径 ──────────────────────────────────────────────────


@pytest.fixture()
def _stub_llm(monkeypatch: pytest.MonkeyPatch):
    """把 LLM 替换成可控的 Runnable，返回指定文本或抛异常。"""

    def _install(output: str | Exception) -> None:
        def _run(_payload: object) -> str:
            if isinstance(output, Exception):
                raise output
            return output

        monkeypatch.setattr(rewrite_module.llm_service, "_llm", RunnableLambda(_run))

    return _install


def test_count_zero_skips_llm(_stub_llm) -> None:
    """count <= 0 时直接返回空，不浪费一次 LLM 调用。"""

    _stub_llm(RuntimeError("不该被调用"))

    assert rewrite_queries("线程是什么", 0) == []
    assert rewrite_queries("线程是什么", -1) == []


def test_success_returns_variants(_stub_llm) -> None:
    """正常改写返回多个查询变体。"""

    _stub_llm('["线程的定义", "线程与进程的区别"]')

    assert rewrite_queries("线程是什么", 2) == ["线程的定义", "线程与进程的区别"]


def test_variant_duplicating_original_is_dropped(_stub_llm) -> None:
    """与原问题相同的变体被剔除，避免同一查询重复参与召回。"""

    _stub_llm('["线程是什么", "线程的定义"]')

    assert rewrite_queries("线程是什么", 2) == ["线程的定义"]


def test_count_truncates_excess_variants(_stub_llm) -> None:
    """超出 count 的变体被截断。"""

    _stub_llm('["a", "b", "c"]')

    assert len(rewrite_queries("q", 2)) == 2


def test_llm_failure_degrades_to_empty(_stub_llm) -> None:
    """LLM 调用失败时返回空列表，绝不中断主链路。"""

    _stub_llm(RuntimeError("上游超时"))

    assert rewrite_queries("线程是什么", 2) == []


def test_unparsable_output_degrades_to_empty(_stub_llm) -> None:
    """模型输出无法解析时降级为空，由调用方退回单查询。"""

    _stub_llm("这段话不是 JSON")

    assert rewrite_queries("线程是什么", 2) == []
