# 环境准备与启动（后端）

> 本页是从项目根 README 拆分出的"如何跑起来"指南，供开发阶段使用。
> 项目级总览（技术栈、目录结构、API 概览等）待项目完成后写入根 `README.md`。

## 1. 启动基础设施（Docker）

```bash
# 在项目根目录执行，复用本地的 pgvector / redis 镜像
docker compose up -d
```

- PostgreSQL：`localhost:5433`（库名 `ai_learning`，用户/密码 `ai_learning`）
- Redis：`localhost:6380`

> 若本地已存在同名镜像会直接复用，不会重复下载。

## 2. 配置环境变量

```bash
cd backend
cp .env.example .env
# 按需修改 .env，至少填入 LLM_API_KEY（或 DeepSeek / Ollama 配置）
```

关键变量见 `.env.example`：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DATABASE_URL` | 数据库连接（注意端口 5433） | `postgresql+psycopg2://ai_learning:ai_learning_123@localhost:5433/ai_learning` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6380/0` |
| `LLM_API_KEY` | 大模型 API Key（OpenAI 兼容，亦可用于 DeepSeek / Ollama） | `sk-your-api-key` |
| `LLM_BASE_URL` | 大模型 API 基址（兼容 DeepSeek / Ollama） | `https://api.openai.com/v1` |
| `LLM_MODEL` | 模型名 | `gpt-4o-mini` |
| `EMBEDDING_API_KEY` | 向量模型 Key（留空复用 `LLM_API_KEY`） | 空 |
| `EMBEDDING_BASE_URL` | 向量模型基址（留空复用 `LLM_BASE_URL`） | 空 |
| `EMBEDDING_MODEL` | 向量模型名 | `text-embedding-3-small` |
| `EMBEDDING_MODEL` | 向量模型 | `text-embedding-3-small` |
| `EMBEDDING_DIM` | 向量维度（需与迁移一致，当前 1536） | `1536` |

## 3. 后端启动（UV）

```bash
cd backend

# 1. 创建虚拟环境并安装依赖
uv venv
uv sync                 # 或 uv pip install -e .

# 2. 初始化数据库（在 backend/ 下执行，使用 backend/alembic.ini，端口 5433）
uv run alembic upgrade head

# 3. 启动服务（默认 http://localhost:8000）
uv run uvicorn app.main:app --reload --port 8000
```

启动后访问交互式 API 文档：<http://localhost:8000/docs>

健康检查：<http://localhost:8000/health>
