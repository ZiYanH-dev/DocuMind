"""配置模块包：配置 + 客户端初始化。"""

from app.config.embedding_client import embedding_service
from app.config.llm_client import llm_service
from app.config.settings import settings

__all__ = ["embedding_service", "llm_service", "settings"]
