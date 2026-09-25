# DocuMind

**上传你的笔记、教材、报告，然后直接问它。**

个人知识库问答助手，基于 Agentic RAG：AI 自主决定何时检索、如何作答，结论均标注出处。

---

## ✨ 特性

- 🤖 **Agentic RAG（LangChain / LangGraph）** —— 检索不再是一条固定流水线：AI 自主判断何时、是否需要调用知识库，多步检索自动编排、按需执行
- 🔍 **三阶段检索引擎** —— 查询改写 → 混合检索（向量 + 关键词）→ 语义重排，层层精筛，换个说法也能命中原文
- 📚 **来源精确溯源** —— 每条回答附引用来源与相关度，可回看文档中对应段落，有据可依
- ⚡ **SSE 实时流式回答** —— 基于 SSE 推流，答案边生成边渲染，长文档问答也无需等待
- 📦 **多格式 · 多用户** —— 支持 PDF / Word / TXT 上传即建库；知识库与对话按用户相互隔离（JWT 鉴权）

## 🛠 技术栈

| 类别 | 技术 |
| --- | --- |
| 前端 | Vue 3 · TypeScript · Vite · Element Plus · Pinia |
| 后端 | Python 3.11+ · FastAPI · Pydantic · SQLAlchemy · Alembic |
| AI 框架 | LangChain · LangGraph |
| 数据存储 | PostgreSQL 17 + pgvector（向量检索）· Redis 6 |
| 基础设施 | Docker · Nginx |

LLM 与向量模型支持 OpenAI / DeepSeek / 本地 Ollama。

## 🚀 快速开始

前置要求：Docker、`uv`、`pnpm`。

```bash
cp .env.example .env   # 填入你的 LLM_API_KEY 等
make start             # 一键启动（自动拉起 Docker / Ollama / 数据库 / 前后端）
```

- 前端页面 `http://localhost:5173`
- 后端 API 文档 `http://localhost:8000/docs`
- 日常管理：`make status` 看状态 · `make stop` 停止 · `make stop-all` 全停

> 缺失的模型或镜像只做提示，不会自动下载。

## ⚙️ 配置

环境变量模板见 `.env.example`（与 Docker Compose 共用一份）。关键项：

| 变量 | 说明 |
| --- | --- |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 大模型（OpenAI / DeepSeek / Ollama） |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_API_KEY` | 向量模型（默认本地 Ollama `nomic-embed-text`） |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` · `REDIS_HOST/PORT/DB` | 数据库与缓存 |
| `SECRET_KEY` · `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT 鉴权 |
| `BACKEND_PORT` / `FRONTEND_PORT` · `MAX_UPLOAD_SIZE_MB` | 端口与上传限制 |

## 🔌 API

除注册 / 登录外，接口均需 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/register` · `/login` · `GET /me` | 注册 / 登录 / 当前用户 |
| POST | `/api/v1/documents/upload` | 上传文档并向量化 |
| GET / DELETE | `/api/v1/documents` · `/documents/{id}` | 文档列表 / 删除 |
| POST / GET / DELETE | `/api/v1/conversations` · `/conversations/{id}` | 会话管理 |
| GET | `/api/v1/conversations/{id}/messages` | 历史消息 |
| POST | `/api/v1/chat` | 流式问答 |

## 📁 项目结构

```
DocuMind/
├── Makefile                    # 一键启动 / 停止 / 质检
├── docker-compose.yml          # 开发编排
├── docker-compose.prod.yml     # 生产编排
├── .env.example
├── backend/                    # FastAPI 后端
│   ├── alembic/                # 数据库迁移
│   ├── Dockerfile
│   └── app/{api,service,repository,schemas,models,agent,retrieval}
├── frontend/                   # Vue 3 + TypeScript 前端
│   ├── Dockerfile · nginx.conf
│   └── src/{api,router,stores,views,components}
└── docs/                       # 需求 / 数据库 / API / 架构 / 部署 文档
```

## 📚 文档

需求、数据库设计、API 规范、架构与部署说明见 [`docs/`](./docs/)。

## License

MIT