# API 接口规范

> Base URL：`/api/v1`，交互式文档：启动后访问 `/docs`（Swagger）。
> 代码位置：路由在 `backend/app/api/v1/`，出入参在 `backend/app/schemas/`。

## 1. 接口总表

除 `/health` 外均需 `Authorization: Bearer <token>`。

| 模块 | 方法 | 路径 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- | --- |
| 系统 | GET | `/health` | — | `{"status": "ok"}` | 健康检查，无需鉴权 |
| 认证 | POST | `/auth/register` | `UserRegister` | `UserOut` | 注册 |
| 认证 | POST | `/auth/login` | `UserLogin` | `TokenOut` | 登录，返回 JWT |
| 认证 | GET | `/auth/me` | — | `UserOut` | 当前用户信息 |
| 文档 | POST | `/documents/upload` | form `file` | `DocumentOut` | 上传并同步解析、分块、向量化 |
| 文档 | GET | `/documents` | query `skip`,`limit` | `DocumentListOut` | 文档列表（分页） |
| 文档 | DELETE | `/documents/{document_id}` | — | `DeleteOut` | 删除文档，含分块与源文件 |
| 会话 | POST | `/conversations` | `ConversationCreate` | `ConversationOut` | 创建会话 |
| 会话 | GET | `/conversations` | query `skip`,`limit` | `ConversationListOut` | 会话列表 |
| 会话 | GET | `/conversations/{conversation_id}/messages` | — | `list[MessageOut]` | 会话消息历史 |
| 会话 | DELETE | `/conversations/{conversation_id}` | — | `DeleteOut` | 删除会话，级联删消息 |
| 问答 | POST | `/chat` | `ChatRequest` | `text/event-stream` | 流式问答，不套信封 |

合计 12 个接口。

## 2. 通用约定

### 2.1 鉴权

令牌由 `POST /auth/login` 返回，后续请求头携带：

```
Authorization: Bearer <access_token>
```

未携带或过期返回 `401`。
`security.py` 用 HS256 签发 JWT，`deps.py` 的 `get_current_user` 负责解析并注入当前用户。

### 2.2 统一响应信封

除 `/chat` 外所有 JSON 接口返回 `ApiResponse[T]`，定义在 `schemas/response.py`：

```json
{ "code": 0, "message": "success", "data": { } }
```

- `code`：业务状态码，`0` 成功，非 `0` 业务异常。
- `message`：提示文案。
- `data`：业务负载，无负载为 `null`。

DELETE 统一返回 `200` + `ApiResponse[DeleteOut]`，`data.id` 为被删资源 ID，不使用 `204`。

### 2.3 错误响应

`core/exceptions.py` 的 `register_exception_handlers` 接管全部异常，错误体同样是信封结构。

| 异常类型 | HTTP | `code` | `data` |
| --- | --- | --- | --- |
| `HTTPException` | 原状态码 | 同 HTTP 状态码 | `null` |
| `AppError` | `exc.status_code` | `exc.code` | `null` |
| `RequestValidationError` | 422 | 1001 | 字段错误数组，元素为 `{field, message}` |
| `SQLAlchemyError` | 500 | 2001 | `null` |
| 其他 `Exception` | 500 | 9999 | `null` |

接管 `HTTPException` 的原因：不接管时 FastAPI 返回 `{"detail": "..."}`，前端读不到 `message`，真实原因会丢成 axios 的默认报错文案。

## 3. 认证 `/auth`

### POST `/auth/register`

请求体 `UserRegister`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| username | string | 是 | 用户名，唯一 |
| email | string | 否 | 邮箱，唯一 |
| password | string | 是 | 明文密码，服务端 bcrypt 哈希 |

响应 `ApiResponse[UserOut]`，`data` 为新建用户，不含密码。

### POST `/auth/login`

请求体 `UserLogin`：`username`、`password`。

响应 `ApiResponse[TokenOut]`：

```json
{ "code": 0, "message": "success",
  "data": { "access_token": "<jwt>", "token_type": "bearer" } }
```

### GET `/auth/me`

需鉴权，响应 `ApiResponse[UserOut]`。

## 4. 文档 `/documents`

### POST `/documents/upload`

表单字段 `file`（multipart）。
支持 `pdf` / `docx` / `txt`，单文件上限 `max_upload_size_mb`，默认 50MB。

处理是同步的，请求会一直阻塞到向量化完成：

1. 校验类型与大小，落盘到 `var/uploads/{user_id}_{8位随机段}_{file_name}`。
2. 解析为纯文本，按 `chunk_size=800`、`chunk_overlap=100` 分块。
3. 批量调用 embedding 接口向量化。
4. 分块入库，文档 `status=completed`。

失败时文档置 `status=failed` 并写入 `error_message`，接口返回 500。
成功后清掉该用户的文档列表缓存、检索结果缓存与 BM25 索引。

响应 `ApiResponse[DocumentOut]`。

`DocumentOut` 字段：
- `id, title, file_name, file_size, file_type, status, error_message, created_at`。

### GET `/documents`

Query：`skip` 默认 0，`limit` 默认 20。
结果按 `{user_id, skip, limit}` 缓存 120 秒。

响应 `ApiResponse[DocumentListOut]`：

```json
{ "code": 0, "message": "success",
  "data": { "total": 12, "items": [ { "id": 1, "title": "..." } ] } }
```

### DELETE `/documents/{document_id}`

校验文档归属当前用户，先删磁盘源文件，再删记录，分块随外键级联删除。
不存在返回 `404`。响应 `200` + `ApiResponse[DeleteOut]`。

## 5. 会话 `/conversations`

### POST `/conversations`

请求体 `ConversationCreate`，`title` 默认"新对话"。
响应 `ApiResponse[ConversationOut]`，字段 `id, title, created_at, updated_at`。

### GET `/conversations`

Query：`skip` 默认 0，`limit` 默认 100。
响应 `ApiResponse[ConversationListOut]`，结构为 `{total, items: [ConversationOut]}`。

### GET `/conversations/{conversation_id}/messages`

响应 `ApiResponse[list[MessageOut]]`。
`MessageOut` 字段：
- `id, role, content, sources, created_at`；
- `sources` 是 `SourceInfo` 数组或 `null`。

### DELETE `/conversations/{conversation_id}`

响应 `200` + `ApiResponse[DeleteOut]`，消息级联删除。

## 6. 问答 `/chat`（SSE 流式）

### POST `/chat`

请求体 `ChatRequest`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| conversation_id | int \| null | 否 | 留空则自动新建会话 |
| content | string | 是 | 用户问题，1 到 8000 字 |

响应头 `Content-Type: text/event-stream`，不套 JSON 信封，逐事件推流。

事件格式为每行一个 `data` 帧，内容是一个含 `type` 与 `content` 的 JSON：

```
data: {"type": "conversation_id", "content": 7}

data: {"type": "token", "content": "根据"}

data: {"type": "token", "content": "文档..."}

data: {"type": "sources", "content": [{"document_id": 1, "document_title": "...", "chunk_index": 0, "snippet": "...", "score": 0.82}]}

data: {"type": "done"}
```

事件类型：

| type | 时机 | content |
| --- | --- | --- |
| `conversation_id` | 首帧 | 本次会话 ID |
| `token` | 生成过程中多次 | 回答的增量文本，前端拼接为完整回答 |
| `sources` | 生成结束前 | 引用来源数组，字段为 `document_id, document_title, chunk_index, snippet, score` |
| `done` | 最后一帧 | 无 |

内部行为：
- 回答由 LangGraph Agent 产出，LLM 自主决定是否调用 `search_knowledge`；
- 只把 `langgraph_node=model` 节点的 token 推给前端，工具内部的中间 LLM 调用被过滤；
- 引用来源来自工具实际命中的片段，按 `document_id` 与 `chunk_index` 去重；
- 历史取最近 10 条消息，读写走 Redis 缓存 600 秒；
- 检索限定当前用户文档，检索细节见 [ai/retrieval.md](./ai/retrieval.md)。

前端用原生 `fetch` 加 `ReadableStream` 消费，浏览器 `EventSource` 不支持 POST 与自定义请求头。

## 7. 状态码速查

| HTTP | 含义 |
| --- | --- |
| 200 | 成功，含 DELETE |
| 400 | 参数错误，如不支持的文件类型、超出大小限制 |
| 401 | 未认证或令牌无效 |
| 404 | 资源不存在，如文档、会话 |
| 422 | 请求体字段校验失败 |
| 500 | 服务器内部错误，如文档处理失败、数据库异常 |
