# API 接口规范

> Base URL：`/api/v1`
> 交互式文档：启动后访问 `/docs`（Swagger）

## 1. 通用约定

### 1.1 鉴权
除 `/health` 外，所有接口需在请求头携带 JWT：

```
Authorization: Bearer <access_token>
```

令牌由 `POST /auth/login` 返回。未携带或过期返回 `401`。

### 1.2 统一响应信封
除 `/chat`（SSE 流）外，所有 JSON 接口均返回 `ApiResponse[T]`：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

- `code`：业务状态码，`0` 成功，非 `0` 业务异常。
- `message`：提示文案。
- `data`：业务负载，类型随接口而定；无负载为 `null`。

> DELETE 接口统一返回 `200` + `ApiResponse[DeleteOut]`（`data.id` 为被删资源 ID），不使用 `204`。

### 1.3 错误响应
业务异常以 HTTP 状态码体现，错误体形如：

```json
{ "detail": "文档不存在" }
```

（统一异常处理层规划中；当前由 FastAPI `HTTPException` 直接返回。）

## 2. 接口清单

### 2.1 认证 `auth`

#### POST `/auth/register`
请求体 `UserRegister`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| username | string | 是 | 用户名 |
| email | string | 否 | 邮箱 |
| password | string | 是 | 明文密码（服务端哈希） |

响应 `ApiResponse[UserOut]`（data = 新建用户，不含密码）。

#### POST `/auth/login`
请求体 `UserLogin`：`username`、`password`。
响应 `ApiResponse[TokenOut]`：

```json
{ "code": 0, "message": "success",
  "data": { "access_token": "<jwt>", "token_type": "bearer" } }
```

#### GET `/auth/me`
需鉴权。响应 `ApiResponse[UserOut]`（当前用户）。

### 2.2 文档 `documents`

#### POST `/documents/upload`
需鉴权。表单字段 `file`（multipart）。支持 `pdf` / `docx` / `txt`，单文件上限 `max_upload_size_mb`（默认 50MB）。
处理流程（同步）：落盘 → 解析 → 分块 → 向量化 → `status=completed`；失败则 `status=failed` 并返回 500。
响应 `ApiResponse[DocumentOut]`（data = 文档元信息，含 `status`）。

#### GET `/documents`
需鉴权。Query：`skip`(默认0)、`limit`(默认20)。
响应 `ApiResponse[DocumentListOut]`：

```json
{ "code": 0, "message": "success",
  "data": { "total": 12, "items": [ { "id": 1, "title": "..." } ] } }
```

`DocumentOut` 字段：`id, title, file_name, file_size, file_type, status, error_message, created_at`。

#### DELETE `/documents/{document_id}`
需鉴权。响应 `200` + `ApiResponse[DeleteOut]`：`{ "data": { "id": 1 } }`；不存在返回 `404`。

### 2.3 会话 `conversations`

#### POST `/conversations`
需鉴权。请求体 `ConversationCreate`：`title`（默认"新对话"）。
响应 `ApiResponse[ConversationOut]`：`id, title, created_at, updated_at`。

#### GET `/conversations`
需鉴权。Query：`skip`(0)、`limit`(100)。
响应 `ApiResponse[ConversationListOut]`：`{ total, items: [ConversationOut] }`。

#### GET `/conversations/{conversation_id}/messages`
需鉴权。响应 `ApiResponse[list[MessageOut]]`。
`MessageOut`：`id, role, content, sources, created_at`（`sources` 为 `SourceInfo` 数组或 null）。

#### DELETE `/conversations/{conversation_id}`
需鉴权。响应 `200` + `ApiResponse[DeleteOut]`：`{ "data": { "id": 1 } }`。

### 2.4 问答 `chat`（SSE 流式）

#### POST `/chat`
需鉴权。请求体 `ChatRequest`：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| conversation_id | int \| null | 否 | 留空则自动新建会话 |
| content | string | 是 | 用户问题（1–8000 字） |

响应：`Content-Type: text/event-stream`。**不使用 JSON 信封**，逐事件推流。

**事件格式**（每行一个 SSE `data` 帧，JSON 含 `type` 与 `content`）：

```
data: {"type": "conversation_id", "content": 7}

data: {"type": "token", "content": "根据"}

data: {"type": "token", "content": "文档..."}

data: {"type": "sources", "content": [{"document_id": 1, "document_title": "...", "chunk_index": 0, "snippet": "...", "score": 0.82}]}

data: {"type": "done"}
```

事件类型：
- `conversation_id`：本次会话 ID（首帧）。
- `token`：回答的增量文本片段，前端拼接为完整回答。
- `sources`：引用来源数组（`SourceInfo`：`document_id, document_title, chunk_index, snippet, score`）。
- `done`：流结束标记。

> 检索严格限定当前用户的文档；仅 `score >= vector_score_threshold`（默认 0.3）的片段进入上下文。历史取最近 10 条消息构成多轮记忆。

### 2.5 系统

#### GET `/health`
无需鉴权。响应 `{"status": "ok"}`（或其他健康检查体）。

## 3. 状态码速查

| HTTP | 含义 |
| --- | --- |
| 200 | 成功（含 DELETE） |
| 400 | 参数错误（不支持的文件类型 / 超出大小限制） |
| 401 | 未认证 / 令牌无效 |
| 404 | 资源不存在（文档 / 会话） |
| 500 | 服务器内部错误（如文档处理失败） |
