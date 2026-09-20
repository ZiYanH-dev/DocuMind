# 接口一览（总表）

> 所有业务接口 Base URL 前缀均为 `/api/v1`。
> 鉴权：除 `/health` 外均需 `Authorization: Bearer <token>`。
> 响应：除 `/chat`（SSE 流）外，统一返回 `ApiResponse[T]` 信封（`{code, message, data}`）；DELETE 统一 `200 + ApiResponse[DeleteOut]`。
> 字段级定义见 [`api-spec.md`](./api-spec.md)。

## 系统

| 方法 | 路径 | 鉴权 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- | --- |
| GET | `/health` | 否 | — | `{"status": "ok"}` | 健康检查 |

## 认证 `/auth`

| 方法 | 路径 | 鉴权 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/register` | 否 | `UserRegister` | `UserOut` | 注册 |
| POST | `/auth/login` | 否 | `UserLogin` | `TokenOut` | 登录，返回 JWT |
| GET | `/auth/me` | 是 | — | `UserOut` | 当前用户信息 |

## 文档 `/documents`

| 方法 | 路径 | 鉴权 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- | --- |
| POST | `/documents/upload` | 是 | form `file` | `DocumentOut` | 上传并解析+向量化（PDF/DOCX/TXT） |
| GET | `/documents` | 是 | query `skip`,`limit` | `DocumentListOut` | 文档列表（分页） |
| DELETE | `/documents/{document_id}` | 是 | — | `DeleteOut` | 删除文档（含分块与文件） |

## 会话 `/conversations`

| 方法 | 路径 | 鉴权 | 请求 | 响应 data | 说明 |
| --- | --- | --- | --- | --- | --- |
| POST | `/conversations` | 是 | `ConversationCreate` | `ConversationOut` | 创建会话 |
| GET | `/conversations` | 是 | query `skip`,`limit` | `ConversationListOut` | 会话列表 |
| GET | `/conversations/{conversation_id}/messages` | 是 | — | `list[MessageOut]` | 会话消息历史 |
| DELETE | `/conversations/{conversation_id}` | 是 | — | `DeleteOut` | 删除会话（级联删消息） |

## 问答 `/chat`（SSE 流式）

| 方法 | 路径 | 鉴权 | 请求 | 响应 | 说明 |
| --- | --- | --- | --- | --- | --- |
| POST | `/chat` | 是 | `ChatRequest` | `text/event-stream` | 流式问答，事件：`conversation_id` → `token*` → `sources` → `done` |

## 统计

| 模块 | 接口数 |
| --- | --- |
| 系统 | 1 |
| 认证 | 3 |
| 文档 | 3 |
| 会话 | 4 |
| 问答（SSE） | 1 |
| **合计** | **12** |

## 状态码速查

| HTTP | 含义 |
| --- | --- |
| 200 | 成功（含 DELETE） |
| 400 | 参数错误（不支持的文件类型 / 超出大小限制） |
| 401 | 未认证 / 令牌无效 |
| 404 | 资源不存在（文档 / 会话） |
| 500 | 服务器内部错误（如文档处理失败） |
