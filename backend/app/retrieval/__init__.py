"""检索模块 —— 多路召回、融合、重排。

对外只暴露 retrieve 与索引缓存失效入口，其余都是实现细节。
"""

from app.retrieval.keyword import invalidate, invalidate_all
from app.retrieval.pipeline import retrieve

__all__ = ["retrieve", "invalidate", "invalidate_all"]
