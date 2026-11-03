# 前端 UI 设计 / 原型说明

> 状态：**规划中**（后端已就绪，前端待开发）
> 技术栈：Vue 3 + TypeScript + Vite + pnpm；状态管理 Pinia；HTTP 客户端 Axios（FetchEventSource 消费 SSE）；UI 库待定（Element Plus / Naive UI 均可）。

## 1. 页面与路由

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/login` `/register` | 登录 / 注册 | 表单提交至 `/auth/login`、`/auth/register` |
| `/documents` | 知识库 | 上传（拖拽/选择）、列表、删除 |
| `/chat` | 问答 | 会话列表 + 对话窗 + 流式回答 + 来源展示 |
| `/` | 重定向 | 依据登录态跳转 |

> 与后端 CORS 默认允许 `http://localhost:5173`（见 `core/config.py` 的 `cors_origins`）。

## 2. 核心交互

### 2.1 知识库页（`/documents`）
- 顶部上传区：拖拽 PDF/DOCX/TXT，调用 `POST /documents/upload`（multipart）。
- 列表卡片：标题、类型、大小、状态徽标（`processing/completed/failed`）、删除按钮（`DELETE /documents/{id}`）。
- 上传后轮询或依赖返回 `status=completed` 提示就绪。

### 2.2 问答页（`/chat`）
- 左侧：会话列表（新建 / 选中 / 删除），调用 `GET/POST/DELETE /conversations`。
- 右侧：消息流（user 右、assistant 左），assistant 消息下方展开「引用来源」卡片（标题 + 片段 + 相似度）。
- 输入框发送：调用 `POST /chat`，**以 SSE 消费**逐 `token` 追加渲染，首帧拿到 `conversation_id` 后绑定当前会话。
- 历史回看：`GET /conversations/{id}/messages` 渲染已有消息。

### 2.3 SSE 消费要点
- 使用 `fetch` + `ReadableStream` 或 `@microsoft/fetch-event-source` 读取 `text/event-stream`。
- 每帧解析 `data:` 后的 JSON：`token` → 追加文本；`sources` → 暂存，流结束后渲染来源；`done` → 结束 loading。
- 维护"回答进行中"状态，禁止在 `done` 前重复发送。

## 3. 页面原型（线框，基于假设）

```
┌───────────────────────────────────────────────┐
│  DocuMind             [知识库] [问答]   [用户]  │
├──────────────┬────────────────────────────────┤
│ 会话         │  用户：什么是 RAG？             │
│ • 论文精读   │                                  │
│ • 教材Q&A    │  AI：RAG 即检索增强生成……（流式）│
│ [+ 新会话]   │  ┌ 来源 ────────────────────┐   │
│              │  │ 教材.pdf · 片段0 · 0.82  │   │
│              │  └──────────────────────────┘   │
│              │  ─────────────────────────────  │
│              │  [ 输入框……………… ]  [发送]      │
└──────────────┴────────────────────────────────┘
```

## 4. 目录建议

```
frontend/
├── src/
│   ├── api/          # axios 实例 + 各模块请求封装（auth/docs/chat…）
│   ├── stores/       # Pinia：auth(token)、conversation
│   ├── views/        # 页面级组件
│   ├── components/   # 上传区 / 消息气泡 / 来源卡片 / 会话列表
│   ├── composables/  # useChatStream（SSE 封装）
│   └── router/       # 路由与登录守卫
└── package.json      # pnpm 管理依赖与脚本
```

## 5. 与后端对接要点

- 所有请求默认带 `Authorization: Bearer <token>`（Pinia 存储，Axios 拦截器注入）。
- 统一解包 `ApiResponse<T>`：`code===0` 取 `data`，否则 toast 错误。
- 上传为同步处理（后端当前实现），前端可显示 loading 直至拿到 `DocumentOut.status`。
- SSE 不套信封，单独处理 `type` 事件流。

> 注：本文件为前端设计说明，具体 UI 库、配色与组件库选型在开发前确定；线框为交互示意，非视觉终稿。
