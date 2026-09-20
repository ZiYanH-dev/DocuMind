"""检索效果评估 —— 对比不同检索配置的召回质量。

用法：
    cd backend
    PYTHONPATH=. uv run python scripts/eval_retrieval.py --user-id 2 --top-k 4 --verbose

指标定义：
    Recall@k  相关片段中被前 k 条结果覆盖的比例
    Hit@k     前 k 条里至少命中一个相关片段的查询占比
    MRR       第一个相关片段名次的倒数，衡量排序质量

评测集按「文档 id + 分块序号」标注，见同目录的 retrieval_eval_cases.json。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.config.database import SessionLocal, engine
from app.config.settings import settings
from app.retrieval import pipeline

# 评测输出只关心指标，压掉 ORM 的 SQL 回显。
# 不能改 logging.getLogger("sqlalchemy.engine") 的级别：APP_DEBUG 打开时
# create_engine(echo=True) 给引擎挂的是 InstanceLogger，改那个名字的级别不生效，
# 直接在引擎上关掉 echo 才有用。
engine.echo = False

CASES_PATH = Path(__file__).resolve().parent / "retrieval_eval_cases.json"

# 逐级打开的检索能力，用于看出每一档各自带来多少提升
CONFIGS: list[tuple[str, dict[str, Any]]] = [
    ("纯向量检索", {"keyword_enabled": False, "rerank_enabled": False, "rewrite_enabled": False}),
    ("关键词 + 向量 混合召回", {"keyword_enabled": True, "rerank_enabled": False, "rewrite_enabled": False}),
    ("混合召回 + Rerank 重排", {"keyword_enabled": True, "rerank_enabled": True, "rewrite_enabled": False}),
    (
        "混合召回 + 重排 + 查询改写",
        {"keyword_enabled": True, "rerank_enabled": True, "rewrite_enabled": True},
    ),
]


def load_cases() -> dict[str, Any]:
    """读取评测集。"""

    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def evaluate(
    session: Session,
    user_id: int,
    cases: list[dict[str, Any]],
    overrides: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    """在给定配置下跑完评测集，返回三项指标与逐条明细。"""

    variant = settings.model_copy(update=overrides)
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    hit_count = 0
    details: list[str] = []

    with patch.object(pipeline, "settings", variant):
        for case in cases:
            results = pipeline.retrieve(
                session, user_id, case["query"], top_k=top_k, use_cache=False
            )
            retrieved = [(int(item["document_id"]), int(item["chunk_index"])) for item in results]
            relevant = {(int(doc), int(idx)) for doc, idx in case["relevant"]}

            ranks = [pos for pos, key in enumerate(retrieved, start=1) if key in relevant]
            recall = len(set(retrieved) & relevant) / len(relevant) if relevant else 0.0
            reciprocal_rank = 1.0 / ranks[0] if ranks else 0.0

            recall_sum += recall
            reciprocal_rank_sum += reciprocal_rank
            hit_count += 1 if ranks else 0

            mark = "命中" if ranks else "未中"
            details.append(
                f"      [{mark}] {case['query'][:28]:<30} "
                f"recall={recall:.2f} rr={reciprocal_rank:.2f} 名次={ranks or '-'}"
            )

    total = len(cases) or 1
    return {
        "recall": recall_sum / total,
        "hit": hit_count / total,
        "mrr": reciprocal_rank_sum / total,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检索效果评估")
    parser.add_argument("--user-id", type=int, required=True, help="评测语料所属的用户")
    parser.add_argument("--top-k", type=int, default=4, help="评估截断位置，默认 4")
    parser.add_argument("--verbose", action="store_true", help="打印每个查询的命中情况")
    args = parser.parse_args()

    data = load_cases()
    cases: list[dict[str, Any]] = data["cases"]

    print("=" * 74)
    print(f"评测集: {data['name']}   查询数: {len(cases)}   top-k = {args.top_k}")
    print("=" * 74)

    with SessionLocal() as session:
        for label, overrides in CONFIGS:
            metric = evaluate(session, args.user_id, cases, overrides, args.top_k)
            print()
            print(f"【{label}】")
            print(
                f"    Recall@{args.top_k} = {metric['recall']:.3f}    "
                f"Hit@{args.top_k} = {metric['hit']:.3f}    "
                f"MRR = {metric['mrr']:.3f}"
            )
            if args.verbose:
                print("\n".join(metric["details"]))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
