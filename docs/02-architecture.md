# 架构与分层

> 后端根目录 `backend/`，源码根 `backend/app/`。
> 分层细节见 [backend/layering.md](./backend/layering.md)，AI 链路见 [ai/agent.md](./ai/agent.md) 与 [ai/retrieval.md](./ai/retrieval.md)。

## 1. 分层与依赖方向

核心五层单向依赖，箭头不可逆：

```
API (路由)  →  Service (业务)  →  Repository (数据访问)  →  Model (ORM)
                  ↑                                          ↑
              Schema (出入参)                            Base (声明)
```

| 层 | 目录 | 职责 | 禁止 |
| --- | --- | --- | --- |
| API | `app/api/v1/` | 路由、鉴权依赖、出入参绑定、HTTP 协议处理 | 写业务逻辑 |
| Service | `app/service/` | 业务编排、事务边界、调 Repository 与 AI 模块 | 直接写 SQL、直接拼 ORM 查询 |
| Repository | `app/repository/` | 封装 SQLAlchemy 查询，含 pgvector 向量检索 | 掺杂业务规则 |
| Model | `app/models/` | ORM 实体，继承 `config/database.Base` | 写业务方法 |
| Schema | `app/schemas/` | Pydantic 出入参，`ApiResponse[T]` 统一信封 | 依赖任何内部层 |

单向依赖由 `tests/unit/test_layering.py` 用 AST 静态校验，越层 import 会让测试失败。

## 2. 旁挂模块

五组模块不属于五层，都在 `backend/app/` 下，按职责被上层单向调用。

| 模块 | 目录 | 职责 | 被谁调用 |
| --- | --- | --- | --- |
| Agent | `app/agent/` | 组装 LangGraph Agent，封装 LLM 可调用的工具 | Service |
| Retrieval | `app/retrieval/` | 查询改写、双路召回、RRF 融合、重排 | Agent、Service |
| Config | `app/config/` | `settings`、`database`、`redis`、`llm_client`、`embedding_client` | 全部模块 |
| Core | `app/core/` | `cache`、`deps`、`exceptions`、`logger`、`middleware`、`security` | 全部模块 |
| Utils | `app/utils/` | 文档解析分块、响应构造 | Service、Retrieval |

`config` 与 `core` 的分工：
- `config` 放配置与客户端实例，启动时一次性初始化；
- `core` 放横切关注点，随每次请求生效。

## 3. 目录结构

```
backend/
├── alembic/versions/       # 0001 建表、0002 embedding 维度 1536→768
├── app/
│   ├── main.py             # 应用入口：中间件、异常处理、路由挂载
│   ├── api/v1/             # auth / documents / conversations / chat
│   ├── service/            # 五层之 Service
│   ├── repository/         # 五层之 Repository
│   ├── schemas/            # 五层之 Schema
│   ├── models/             # 五层之 Model
│   ├── agent/              # agent.py 组装、tools.py 工具
│   ├── retrieval/          # pipeline / rewrite / keyword / fusion / rerank
│   ├── config/             # settings.py、app.yaml、database、redis、两个客户端
│   ├── core/               # cache / deps / exceptions / logger / middleware / security
│   └── utils/              # document_parser / response
├── tests/                  # unit / service / http / integration 四层
└── scripts/                # 检索评测脚本
```

## 4. 一次问答请求的调用链

```
POST /api/v1/chat
  └─ api/v1/chat.py                 ChatRequest 校验、get_current_user 依赖
       └─ service/chat_service.py
            ├─ conversation_repository                    取或建会话
            ├─ core/cache  history_key                    读历史缓存，未命中查库回填
            ├─ message_repository.create("user")          落库用户提问
            ├─ agent/agent.py  create_chat_agent()        按请求新建 Agent
            │    └─ agent/tools.py  build_tools()         闭包绑定 session 与 user_id
            ├─ bundle.agent.stream(stream_mode=["updates","messages"])
            │    ├─ LLM 决定调用 search_knowledge
            │    │    └─ retrieval/pipeline.retrieve()    改写 → 双路召回 → 融合 → 重排
            │    ├─ updates 事件：收集工具名，写链路日志
            │    └─ messages 事件：只取 model 节点的 token
            ├─ message_repository.create("assistant")     落库回答与引用
            └─ core/cache  history_key 回写               下一轮免查库
       → 逐条 yield dict 事件 → api 包装为 SSE `data:` 帧
```

工具调用自己也会产生 LLM 流，若不按 `langgraph_node` 过滤，检索改写的中间产物会被当成回答推给前端。
实现见 `ChatService._extract_token`，细节见 [ai/agent.md](./ai/agent.md)。

## 5. 一次上传请求的调用链

```
POST /api/v1/documents/upload
  └─ api/v1/documents.py
       └─ service/document_service.py
            ├─ 校验类型与大小 → 落盘 var/uploads/
            ├─ document_repository.create(status=processing)
            ├─ utils/document_parser  解析 → 分块
            ├─ config/embedding_client  批量向量化
            ├─ chunk_repository.create_many  分块入库
            ├─ document_repository.update_status(completed)
            └─ _invalidate_user   清文档列表缓存、检索缓存、BM25 索引
```

## 6. 质量门禁

入口统一在项目根 `Makefile`。

| 门禁 | 命令 | 说明 |
| --- | --- | --- |
| 后端静态检查 | `make be-check` | `ruff check` 加 `ruff format --check`，覆盖 `app/`、`tests/`、`scripts/` |
| 前端类型检查 | `make fe-check` | `vue-tsc --noEmit` |
| 一站式检查 | `make verify` | 前两条的组合 |
| 分层校验 | `make be-test-unit` | 其中 `test_layering.py` 用 AST 校验越层依赖 |
| 全量后端测试 | `make be-test` | 需 Docker 与 `documind_test` 库已就绪 |
| 覆盖率 | `make be-test-cov` | `--cov=app --cov-report=term-missing` |
| 端到端 | `make e2e` | 打真实端口，服务需先 `make start` 拉起 |
| 持续集成 | GitHub Actions | push 到 main 与提 PR 时自动跑上述检查，配置在 `.github/workflows/ci.yml` |

`pyproject.toml` 里写了 `mypy` 的 strict 配置，但 `mypy` 不在 dev 依赖组，当前不构成门禁。
补装后 `uv run mypy app` 才可用。

测试分层与替身写法见 [backend/testing.md](./backend/testing.md)。

## 7. 已知债务

| 项 | 现状 | 目标 |
| --- | --- | --- |
| Service 层抛 `HTTPException` | 四个 service 共 9 处 | 改抛 `AppError` 子类，让 Service 可在非 HTTP 上下文复用 |
| `AppError` 无业务抛出 | handler 已注册但无 `raise` | 随上一条一并解决 |
| `mypy` 未入依赖 | 只写了 strict 配置 | 加进 dev 依赖并把命令接进 `make be-check` |
| Python 大版本不一致 | 镜像与 CI 用 3.11，`ruff` 的 `target-version` 与 `mypy` 的 `python_version` 写 3.12，本地 venv 是 3.12 | 统一到 3.11，或把镜像升到 3.12 |

前两条在 `test_layering.py` 里用 `xfail(strict=True)` 登记，修复后测试报 XPASS，提醒摘除标记。

## 8. 关键技术选型

| 项 | 选型 | 关键参数 |
| --- | --- | --- |
| Web 框架 | FastAPI + uvicorn | 路由前缀 `/api/v1` |
| ORM | SQLAlchemy 2.0 `Mapped` 写法 | 全仓库统一 ORM，无手写 SQL |
| 数据库 | PostgreSQL 17 + pgvector | 端口 5433，IVFFlat 索引 `lists=100` |
| 缓存 | Redis 6 | 三个命名空间，见 [ai/indexing.md](./ai/indexing.md) |
| Agent | LangGraph `create_agent` | `langchain>=1.0`、`langgraph>=1.2` |
| LLM 接入 | `ChatOpenAI` OpenAI 兼容协议 | 换基址即换 provider，无开关 |
| 检索 | 混合召回 + RRF + 百炼重排 | 每路可关，关后自动退化 |
| 前端 | Vue 3 + TS + Vite + Pinia + Element Plus | 见 [frontend/design.md](./frontend/design.md) |
