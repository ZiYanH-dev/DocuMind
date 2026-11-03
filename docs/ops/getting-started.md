# 环境准备与启动（开发指南）

> 开发环境快速跑通指南。推荐用 **Makefile 一键命令**，也可手动分步执行。
> 生产部署见 [deployment.md](./deployment.md)。

## 前置依赖

| 工具 | 用途 |
| --- | --- |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | PostgreSQL + Redis |
| [uv](https://docs.astral.sh/uv/) | Python 包管理 |
| [pnpm](https://pnpm.io/) | 前端包管理 |
| [Ollama](https://ollama.com/) | 本地 Embedding 模型（如用云端则不装） |

## 1. 配置环境变量

`.env` 放在**项目根目录**（不是 `backend/`），从模板复制：

```bash
# 项目根目录
cp .env.example .env
```

> ⚠️ `settings.py` 固定读 `REPO_ROOT/.env`（根目录）。不要 `cd backend` 复制，`backend/.env` 永远不会被加载。

按需修改，**至少填 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`**（`.env.example` 内置了云厂商与 DeepSeek / Ollama 三套样例）。

### 配置分两组，别混

**A. 接入配置 / 密钥 → 根目录 `.env`**（机密，进 `.gitignore`）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `BACKEND_PORT` | 后端端口 | `8000` |
| `FRONTEND_PORT` | 前端端口 | `5173` |
| `APP_ENV` | 环境（development/production） | `development` |
| `APP_DEBUG` | 调试开关（控制 SQL echo、日志级别） | `true` |
| `SECRET_KEY` | JWT 签名密钥，**生产必须改** | `change-me-...` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 令牌有效期 | `1440` |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | 数据库（分字段，URL 由 `settings.py` 拼接） | `localhost/5433/documind/documind/documind` |
| `REDIS_HOST/PORT/DB` | Redis（分字段） | `localhost/6380/0` |
| `LLM_API_KEY` | 大模型 Key（OpenAI 兼容） | `sk-your-api-key` |
| `LLM_BASE_URL` | 大模型基址 | 见 `.env.example` |
| `LLM_MODEL` | 模型名 | `qwen-max` |
| `EMBEDDING_API_KEY` | 向量 Key（留空复用 `LLM_API_KEY`） | `ollama` |
| `EMBEDDING_BASE_URL` | 向量基址 | `http://localhost:11434/v1` |
| `EMBEDDING_MODEL` | 向量模型 | `nomic-embed-text` |
| `MAX_UPLOAD_SIZE_MB` | 上传大小上限 | `50` |

**B. 非机密超参 → `backend/app/config/app.yaml`**（进 git，改温度、分块、检索参数）

| 段 | 键 | 默认 |
| --- | --- | --- |
| `llm` | `temperature` / `max_tokens` | `0.7` / `2048` |
| `embedding` | `dim` | `768` |
| `retrieval` | `top_k` / `score_threshold` / `keyword_enabled` / `rewrite_enabled` / `rerank_enabled` ··· | `4` / `0.3` / `true` / `true` / `true` |
| `parser` | `chunk_size` / `chunk_overlap` | `800` / `100` |

> ⚠️ `embedding.dim` 必须与数据库 `document_chunks.embedding` 向量维度一致（当前 `768`，已由 `0002_alter_embedding_dim` 迁移对齐）。

## 2. 首个模型（如用本地 Ollama）

若 `.env` 里 `EMBEDDING_BASE_URL` 指向 localhost，需先有 Ollama 并拉好嵌入模型：

```bash
ollama pull nomic-embed-text
```

## 3. 一键启动（推荐）

```bash
make init   # 首次初始化：装依赖 → 起 Docker → 跑迁移
make start  # 一键启动全部（Ollama → Docker → DB → 迁移 → 后端 → 前端）
make status # 查看全部服务状态
make stop   # 停止前后端（保留 Docker + Ollama）
```

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 前端页面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 健康检查 | http://localhost:8000/health |

## 4. 手动分步启动（不依赖 Makefile）

```bash
# 4.1 基础设施（项目根目录）
docker compose up -d

# 4.2 后端
cd backend
uv sync               # 安装依赖
uv run alembic upgrade head   # 建表（端口 5433）
uv run uvicorn app.main:app --reload --port 8000

# 4.3 前端（另开终端，项目根目录）
cd frontend
pnpm install
pnpm dev
```

## 5. 完整命令速查

```bash
make be-check      # 后端 ruff 检查
make be-format     # 后端 ruff 自动格式化
make be-test       # 后端 pytest
make fe-check      # 前端 vue-tsc 类型检查
make be-logs       # 看后端日志（后台启动时）
make fe-logs       # 看前端日志（后台启动时）
make db-shell      # 进入 psql
make redis-shell   # 进入 redis-cli
make stop-all      # 全部停止（含 Docker + Ollama）
```