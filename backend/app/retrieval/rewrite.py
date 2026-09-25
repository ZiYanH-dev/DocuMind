"""查询改写 —— 生成多个查询变体用于多路召回。

用户的提问措辞往往与文档里的表述不一致，单条查询容易漏召。让模型把原问题改写成
几个不同角度的查询，各自参与召回，再由融合层合并，能提高召回覆盖面。

改写只影响召回范围，失败时退回单查询检索，不中断主链路。
"""

from __future__ import annotations

import json
import logging
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.config.llm_client import llm_service

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """你是检索查询改写助手。把用户的问题改写成 {count} 个不同角度的检索查询，用于在知识库中召回相关文档片段。

要求：
1. 每条查询独立可用，不依赖上下文。
2. 从不同角度切入，覆盖原问题的不同侧面，避免同义重复。
3. 保留问题中的专有名词与技术术语原样。
4. 只输出一个 JSON 字符串数组，不要输出解释文字。

用户问题：{question}"""

# 模型有时会把 JSON 包在代码块围栏里，先剥掉围栏再解析
_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)


def _parse_queries(raw: str) -> list[str]:
    """从模型输出里解析查询列表，解析不出来就返回空列表。"""

    text = _FENCE.sub("", raw).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("rewrite output is not json: %r", raw[:120])
        return []

    if not isinstance(parsed, list):
        return []

    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def rewrite_queries(question: str, count: int) -> list[str]:
    """生成额外的查询变体，失败时返回空列表让调用方退回单查询检索。"""

    if count <= 0:
        return []

    prompt = ChatPromptTemplate.from_template(REWRITE_PROMPT)
    chain = prompt | llm_service.llm | StrOutputParser()

    # 改写仅用于扩大召回面，任何异常都应降级而不是中断整轮问答
    try:
        raw = chain.invoke({"question": question, "count": count})
    except Exception as exc:  # noqa: BLE001
        logger.warning("rewrite failed, fallback to original query: %s", exc)
        return []

    queries = _parse_queries(raw)
    # 剔除与原问题重复的变体，避免同一查询重复参与召回
    return [query for query in queries if query != question][:count]
