# AI 智能学习助手

基于知识库的智能问答系统：上传学习资料（PDF / Word / TXT），系统自动解析、分块、向量化，
并通过 RAG（检索增强生成）+ 流式对话，帮助用户高效学习与复习。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + TypeScript + pnpm（规划中） |
| 后端 | FastAPI（Python 3.11+） |
| 数据库 | PostgreSQL 16 + pgvector（向量检索） |
| 缓存 / 中间件 | Redis 7 |
| AI | LangChain（LLM / Embedding / 文本分块） |
| 包管理 | 后端 UV、前端 pnpm |
| 基础设施 | Docker（PostgreSQL、Redis 镜像复用） |

支持的 LLM / Embedding 提供方：OpenAI、DeepSeek（OpenAI 兼容）、Ollama（本地）。

## 目录结构

```
study_helper/
├── alembic.ini              # 根 Alembic 配置（指向 backend/alembic）
├── docker-compose.yml       # PostgreSQL(pgvector) + Redis
├── backend/                 # FastAPI 后端
│   ├── alembic.ini          # 后端 Alembic 配置（从 backend/ 运行迁移时用）
│   ├── alembic/             # 迁移脚本（versions/）
│   ├── pyproject.toml       # 依赖与工具配置（ruff / mypy）
│   ├── .env.example         # 环境变量样例
│   └── app/
│       ├── main.py          # 应用入口
│       ├── api/             # 路由层（API）
│       │   └── v1/          #   auth / documents / conversations / chat
│       ├── service/         # 业务服务层（Service，五层之一）
│       ├── repository/      # 数据访问层（Repository，五层之一）
│       ├── schemas/         # 请求/响应模型（Schema，五层之一）
│       ├── models/          # ORM 模型（Model，五层之一）
│       ├── integrations/    # 第三方技术集成（LLM / Embedding / 文档解析）
│       ├── core/            # 配置 / 数据库 / 安全 / 依赖（基础设施）
│       └── utils/           # 通用工具
└── docs/                    # 详细文档（需求 / 数据库设计 / API 规范 / 架构，规划中）
```

> 后端严格遵循五层单向调用：`api → service → repository → models`。
> `integrations` / `core` / `utils` 属于"其他"支撑模块，不计入五层核心。

## 环境准备

### 1. 启动基础设施（Docker）

```bash
# 在项目根目录执行，复用本地的 pgvector / redis 镜像
docker compose up -d
```

- PostgreSQL：`localhost:5433`（库名 `ai_learning`，用户/密码 `ai_learning`）
- Redis：`localhost:6380`

> 若本地已存在同名镜像会直接复用，不会重复下载。

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
# 按需修改 .env，至少填入 OPENAI_API_KEY（或 DeepSeek / Ollama 配置）
```

关键变量见 `.env.example`：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DATABASE_URL` | 数据库连接（注意端口 5433） | `postgresql+psycopg2://ai_learning:ai_learning_123@localhost:5433/ai_learning` |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6380/0` |
| `LLM_PROVIDER` | `openai` / `deepseek` / `ollama` | `openai` |
| `OPENAI_API_KEY` | API Key | `sk-your-api-key` |
| `OPENAI_BASE_URL` | API 基址（兼容 DeepSeek / Ollama） | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 模型名 | `gpt-4o-mini` |
| `EMBEDDING_MODEL` | 向量模型 | `text-embedding-3-small` |
| `EMBEDDING_DIM` | 向量维度（需与迁移一致，当前 1536） | `1536` |

## 后端启动（UV）

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

## API 概览

所有业务接口除 `/health` 外均需 `Authorization: Bearer <token>` 鉴权（注册/登录除外）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/register` | 用户注册 |
| POST | `/api/v1/auth/login` | 用户登录，返回 JWT |
| GET | `/api/v1/auth/me` | 获取当前用户信息 |
| POST | `/api/v1/documents/upload` | 上传文档（PDF / Word / TXT），自动解析+向量化 |
| GET | `/api/v1/documents` | 文档列表 |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |
| POST | `/api/v1/conversations` | 创建会话 |
| GET | `/api/v1/conversations` | 会话列表 |
| GET | `/api/v1/conversations/{id}/messages` | 会话消息历史 |
| DELETE | `/api/v1/conversations/{id}` | 删除会话 |
| POST | `/api/v1/chat` | 流式问答（SSE，`text/event-stream`） |
| GET | `/health` | 健康检查（无鉴权） |

问答接口（`/chat`）返回 SSE 事件流，事件 `type` 包括 `token`（增量文本）、`sources`（引用来源）、`done`（结束）等。

## 统一响应格式

除 `/chat` 的 SSE 流式接口外，所有 JSON 接口均返回统一的 `ApiResponse[T]` 信封：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

- `code`：业务状态码，`0` 表示成功，非 `0` 表示业务异常。
- `message`：提示信息。
- `data`：业务数据负载，类型随接口不同（如 `UserOut`、`DocumentListOut`、`DeleteOut` 等）；无负载时为 `null`。

约定：
- 所有接口都返回信封，DELETE 不再使用 `204 No Content`，统一 `200` + `ApiResponse[DeleteOut]`（`data` 含被删资源 `id`）。
- `/chat` 为 `text/event-stream` 流式响应，按 SSE 事件（`token` / `sources` / `done`）逐条推送，不适用信封。

## 开发规范要点

后端统一遵循以下约定（详见 `docs/architecture.md`，规划中）：

- **分层**：`api → service → repository → models` 单向调用；`Schema` 负责出入参。
- **类型注解**：函数参数、返回值必须标注类型；无返回显式标 `-> None`。
- **命名**：类 `PascalCase`、文件/函数/变量 `snake_case`、常量 `UPPER_SNAKE`、私有 `_xxx`。
- **导入顺序**：标准库 → 第三方库 → 项目内部，组间空行、组内字母序；禁止 `import *`（仅 `__init__` 导出场景例外）。
- **注释**：模块 / 类 / 函数文档字符串 + 必要行内注释。
- **代码质量**：`ruff` 与 `mypy(strict)` 已配置，提交前建议 `uv run ruff check .` 与 `uv run mypy app`。

## 后续规划

- 统一异常处理层（当前异常由 FastAPI `HTTPException` 直接返回，尚未包装进 `ApiResponse` 风格）。
- 文档处理异步化（当前 `/documents/upload` 为同步处理，后续可改为任务队列 + 状态轮询）。
- 前端：Vue 3 + pnpm 实现上传、会话、流式问答界面，并与后端联调（设计见 `docs/frontend-design.md`）。

> 详细设计文档见项目 `docs/` 目录（需求 / 数据库 / API / 架构 / 前端），导航见 [`docs/README.md`](./docs/README.md)。
