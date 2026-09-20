"""应用配置模块。"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/），与 CWD 无关
# settings.py = backend/app/config/settings.py → 上3级 = backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent  # 项目根目录（.env 所在）


def load_ai_config() -> dict:
    """读取 AI 非机密配置 app.yaml（与 settings.py 同目录），启动即 fail-fast。"""

    path = Path(__file__).resolve().parent / "app.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data

# AI 配置默认值来源（YAML，进 git）；.env 可作为覆盖项
_AI = load_ai_config()


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        frozen=True,
        extra="ignore",
    )

    # ===== 应用 =====
    app_name: str = "AI Learning Assistant"
    app_env: str = "development"
    app_debug: bool = True
    secret_key: str = "change-me-to-a-random-secret-key"
    access_token_expire_minutes: int = 1440

    # ===== 数据库（分字段，URL 由 resolved_database_url 推导）=====
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "ai_learning"
    postgres_password: str = "ai_learning_123"
    postgres_db: str = "ai_learning"

    # ===== Redis（分字段）=====
    redis_host: str = "localhost"
    redis_port: int = 6380
    redis_db: int = 0

    @property
    def resolved_database_url(self) -> str:
        """拼接数据库连接串。"""

        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def resolved_redis_url(self) -> str:
        """拼接 Redis 连接串。"""

        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ===== CORS（开发端口由 frontend_port 派生；cors_origins 非空则覆盖）=====
    frontend_port: int = 5173  # 读 .env: FRONTEND_PORT
    cors_origins: str = ""  # 空 → 按 frontend_port 派生；非空 → 自定义

    # ===== LLM（OpenAI 兼容接口，可对接 DeepSeek / Ollama 等）=====
    llm_api_key: str = "sk-your-api-key"
    llm_base_url: str = ""  # 来自 .env: LLM_BASE_URL
    llm_model: str = ""  # 来自 .env: LLM_MODEL
    llm_temperature: float = _AI["llm"]["temperature"]
    llm_max_tokens: int = _AI["llm"]["max_tokens"]

    # ===== Embedding（OpenAI 兼容接口，默认与 LLM 同基址）=====
    embedding_api_key: str | None = None  # 留空则复用 llm_api_key
    embedding_base_url: str | None = ""  # 来自 .env: EMBEDDING_BASE_URL  # None 则复用 llm_base_url
    embedding_model: str = ""  # 来自 .env: EMBEDDING_MODEL
    embedding_dim: int = _AI["embedding"]["dim"]

    @property
    def effective_embedding_api_key(self) -> str:
        """实际用于向量化的 API Key（缺省复用 LLM 的 Key）。"""

        return self.embedding_api_key or self.llm_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        """实际用于向量化的基址（缺省复用 LLM 的基址）。"""

        return self.embedding_base_url or self.llm_base_url

    # ===== 向量检索 =====
    vector_top_k: int = _AI["retrieval"]["top_k"]
    vector_score_threshold: float = _AI["retrieval"]["score_threshold"]

    # ===== 文档解析 =====
    upload_dir: str = str(REPO_ROOT / "var" / "uploads")
    max_upload_size_mb: int = 50
    chunk_size: int = _AI["parser"]["chunk_size"]
    chunk_overlap: int = _AI["parser"]["chunk_overlap"]

    # ===== 日志 =====
    log_dir: str = str(REPO_ROOT / "var" / "logs")
    log_file: str = "app.log"

    @field_validator("log_dir", mode="after")
    @classmethod
    def resolve_log_dir(cls, v: str) -> str:
        """将 log_dir 解析为绝对路径并确保目录存在。"""

        path = Path(v)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def log_path(self) -> Path:
        """日志文件完整路径。"""

        return Path(self.log_dir) / self.log_file

    @field_validator("upload_dir", mode="after")
    @classmethod
    def resolve_upload_dir(cls, v: str) -> str:
        """将 upload_dir 解析为绝对路径（支持 .env 中写相对路径）。"""

        path = Path(v)
        if not path.is_absolute():
            path = BASE_DIR / path
        # 确保目录存在
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS 允许的域名列表（缺省由前端端口派生）。"""

        if self.cors_origins.strip():
            return [
                origin.strip()
                for origin in self.cors_origins.split(",")
                if origin.strip()
            ]
        return [
            f"http://localhost:{self.frontend_port}",
            f"http://127.0.0.1:{self.frontend_port}",
        ]


@lru_cache
def get_settings() -> Settings:
    """获取全局配置实例（缓存）。"""

    return Settings()


settings = get_settings()
