# 架构与分层规范

## 1. 分层架构

严格遵循核心五层，**单向调用**：

```
API (路由)  →  Service (业务)  →  Repository (数据访问)  →  Model (ORM)
                  ↑                                          ↑
              Schema (出入参)                            Base (声明)
```

- **API（`app/api`）**：路由与 HTTP 协议处理，负责鉴权依赖、请求/响应模型绑定，**不含业务逻辑**。
- **Service（`app/service`）**：业务逻辑层，编排 Repository 与 `integrations`，事务边界所在。
- **Repository（`app/repository`）**：封装 SQLAlchemy 数据访问，不掺杂业务规则。
- **Model（`app/models`）**：ORM 实体，继承 `core.database.Base`。
- **Schema（`app/schemas`）**：Pydantic 请求/响应模型；`response.ApiResponse[T]` 为统一信封。
- **支撑模块（非五层）**：
  - `integrations`：第三方技术集成（LLM / Embedding / 文档解析），与原 `services` 包收敛而来。
  - `core`：配置 `config`、数据库 `database`、安全 `security`、依赖注入 `deps`。
  - `utils`：通用工具（如响应构造）。

## 2. 目录结构

```
backend/app/
├── main.py                 # 应用入口（挂载路由、CORS、生命周期）
├── api/v1/                 # auth / documents / conversations / chat
├── service/                # 业务服务（五层之一）
├── repository/             # 数据访问（五层之一）
├── schemas/                # 入参/出参 + response 信封
├── models/                 # ORM 实体（五层之一）
├── integrations/           # LLM / Embedding / 文档解析
├── core/                   # config / database / security / deps
└── utils/                  # 通用工具
```

## 3. 一次问答请求的调用链

```
POST /api/v1/chat
  └─ api/v1/chat.py           (ChatRequest 校验, get_current_user 依赖)
       └─ service/chat_service.py
            ├─ conversation_repository / message_repository  (会话/消息)
            ├─ integrations/embedding_service.embed_query()   (query 向量化)
            ├─ repository/chunk_repository.vector_search()    (pgvector 余弦检索, 按 user_id 过滤)
            ├─ integrations/llm_service.stream_chat()         (LLM 流式生成)
            └─ message_repository.create(user/assistant)      (落库)
       → 以 dict 事件 yield → api 包装为 SSE `data:` 帧推流
```

## 4. 编码规范 Checklist（落地要求）

### 类型注解
- [ ] 函数参数、返回值**必须**标注类型；无返回显式 `-> None`。
- [ ] 简单局部变量若推导清晰可省略；空容器 / 嵌套结构 / 自定义模型实例**必须**显式标注。
- [ ] 类属性写在类体（`class-attribute`），实例属性用 `self.xxx` 在 `__init__` 赋值；私有 `_xxx`。

### 命名
- [ ] 类 `PascalCase`；函数 / 变量 / 文件 `snake_case`；常量 `UPPER_SNAKE`。
- [ ] 私有成员单下划线 `_xxx`；不自创魔法方法 `__xxx__`。

### 导入
- [ ] 业务逻辑**优先绝对导入**（`from app.xxx import yyy`）。
- [ ] 仅 `__init__.py` 导出场景允许少量相对导入与 `import *`。
- [ ] 顺序：标准库 → 第三方库 → 项目内部；组间空行、组内字母序。

### 注释
- [ ] 模块、类、公共函数 / 方法均写文档字符串（docstring）。
- [ ] 关键逻辑补行内注释。

### 响应一致性
- [ ] 所有 JSON 接口经 `ApiResponse[T]` 返回；DELETE 用 `200 + DeleteOut`。
- [ ] `/chat` SSE 流不套信封，按 `token/sources/done` 事件推送。

### 质量门禁
- [ ] 提交前 `uv run ruff check .` 与 `uv run mypy app`（strict）零告警。
- [ ] 后端自测：`uv run pytest`（dev 依赖组），主链路集成测试见 `tests/test_main_flow.py`。

### 测试结构
- `tests/conftest.py`：复用本地 PostgreSQL（docker 端口 5433）的测试库 `ai_learning_test`，会话级建表、用例级事务回滚，并覆盖 `get_db` 依赖注入测试会话。
- `tests/test_main_flow.py`：TestClient 集成测试，覆盖 注册→登录→文档上传/列表/删除→会话流程，验证统一 `ApiResponse` 信封与 Bearer 鉴权。
- 文档上传为同步处理会真实调用 Embedding；跑通需配置可用 `LLM_API_KEY`（Embedding 缺省复用），或在测试中 mock `app.integrations.embedding_service`。

## 5. 关键技术点

- **RAG 流程**：解析 → 分块（`chunk_size=800`, `overlap=100`）→ 向量化（`text-embedding-3-small`, 1536 维）→ 入库；检索取 `top_k=4` 并按 `score>=0.3` 过滤。
- **向量检索**：pgvector 类型自带 `cosine_distance()` ORM 表达式（生成 `embedding <=> :param`），经 `ChunkRepository.vector_search` 用纯 SQLAlchemy `select` 完成；相似度 `score = 1 - distance`，IVFFlat 索引（`lists=100`），按 `user_id` 隔离。**全仓库统一走 ORM，无手写 SQL。**
- **鉴权**：JWT（HS256，`access_token_expire_minutes=1440`），`HTTPBearer` 解析，`get_current_user` 依赖注入。
- **多提供方（OpenAI 兼容接口）**：通过 `LLM_BASE_URL` / `EMBEDDING_BASE_URL` 切换 openai / deepseek / ollama（本地），无需 provider 开关；embedding 的 Key/基址缺省复用 LLM 配置。
