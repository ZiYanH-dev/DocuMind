# 前端设计与实现

> 状态：**已实现**，登录、知识库、问答三个页面可跑通。
> 代码：`frontend/src/`，技术栈 Vue 3 + TS + Vite + pnpm + Pinia + Element Plus + Axios。

## 1. 技术栈与入口

| 项 | 版本 / 选型 | 落点 |
| --- | --- | --- |
| 框架 | Vue 3.5，`<script setup>` | `src/App.vue` |
| 构建 | Vite 8 | `vite.config.ts` |
| 语言 | TypeScript 6，构建时 `vue-tsc -b` 先做类型检查 | `package.json` |
| UI 库 | Element Plus 2.8，中文语言包 `zhCn` | `src/main.ts` |
| 状态 | Pinia 2，组合式写法 | `src/stores/user.ts` |
| 路由 | vue-router 4，`createWebHistory` | `src/router/index.ts` |
| HTTP | Axios 1.7，统一拦截器 | `src/api/request.ts` |

`vite.config.ts` 把 `/api` 代理到 `http://localhost:8000`，并对 `text/event-stream` 响应关掉缓冲：
设置 `cache-control: no-cache, no-transform` 与 `x-accel-buffering: no`，否则 token 会被攒批，流式效果消失。

## 2. 路由

| 路由 | 组件 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| `/login` | `views/Login.vue` | 否 | 登录与注册在同一页切换 |
| `/chat` | `views/Chat.vue` | 是 | 默认页，`/` 重定向到这里 |
| `/documents` | `views/Documents.vue` | 是 | 知识库 |
| 其他 | `views/NotFound.vue` | 否 | 通配 404 |

`/chat` 与 `/documents` 挂在 `components/layout/MainLayout.vue` 下作为子路由，共用顶部导航。

守卫逻辑在 `router.beforeEach`：
- `meta.requiresAuth !== false` 且 `localStorage` 无 `access_token` 时跳到 `/login`，带 `redirect` 查询参数；
- 已登录访问 `/login` 时跳 `/chat`；
- 其余放行。

## 3. 目录结构

```
frontend/src/
├── main.ts             # 挂 Pinia、Router、Element Plus，注册全部图标
├── App.vue
├── api/
│   ├── request.ts      # axios 实例、拦截器、ApiResponse 类型
│   ├── auth.ts         # 三个认证接口
│   ├── document.ts     # 上传、列表、删除
│   └── conversation.ts # 会话与消息
├── stores/user.ts      # token、userInfo、login/register/logout
├── composables/useChat.ts   # 会话状态 + SSE 流式消费
├── views/              # Login / Chat / Documents / NotFound
├── components/
│   ├── layout/MainLayout.vue
│   ├── chat/           # ChatSidebar / MessageList / MessageItem / ChatInputBar
│   └── documents/      # FileUploadArea / DocumentTable
├── router/index.ts
└── utils/index.ts
```

目录职责：

| 目录 | 只放什么 |
| --- | --- |
| `api/` | 请求封装与出入参类型，不写状态 |
| `stores/` | 跨页面共享状态，当前只有用户态 |
| `composables/` | 有状态的逻辑复用，当前只有 `useChat` |
| `components/` | 通过 props 收参、emit 抛事件，不调接口、不引 store |

## 4. 请求层

`api/request.ts` 定义 axios 实例与两层拦截：

| 拦截 | 行为 |
| --- | --- |
| 请求拦截 | 从 `localStorage` 取 `access_token`，注入 `Authorization: Bearer` |
| 响应拦截 | `code === 0` 时返回 `data`，否则 `ElMessage` 提示并抛出 |

类型上定义 `ApiResponse<T>` 与 `ApiErrorBody`。
错误优先读统一信封的 `message`，`detail` 作为兼容兜底。
401 时清 token 并跳登录页。

## 5. 问答页的流式消费

`composables/useChat.ts` 用原生 `fetch` 加 `ReadableStream`，不用 `EventSource`。
原因：`EventSource` 只支持 GET，无法带 POST 请求体与自定义请求头。

消费流程：

1. `AbortController` 建信号，支持中途停止生成。
2. `fetch('/api/v1/chat')`，手动带 `Authorization` 头与 JSON 请求体。
3. `response.body.getReader()` 配 `TextDecoder`，按 `\n` 切行，残片留在 buffer。
4. 只处理 `data: ` 前缀的行，`JSON.parse` 后按 `type` 分发：
   - `token` 追加到当前 assistant 消息的 `content`；
   - `sources` 写入该消息的 `sources`；
   - `conversation_id` 与 `done` 不渲染。
5. `finally` 里复位 `isGenerating` 并刷新会话列表。

发送前若 `conversationId` 为空，先调 `POST /conversations` 建会话。
竞态处理：保存发送前的会话 ID，流结束回写时只有当会话未被切换才更新消息。

## 6. 知识库页

`components/documents/FileUploadArea.vue` 负责拖拽与选择文件，`DocumentTable.vue` 渲染列表。
状态徽标对应后端 `processing`、`completed`、`failed` 三态，失败时展示 `error_message`。

上传是同步接口，前端在请求未返回前显示 loading，拿到 `DocumentOut.status` 后刷新列表。
不需要轮询，因为后端在返回前已经处理完。

## 7. 与后端对接要点

| 项 | 约定 |
| --- | --- |
| 鉴权 | 全部请求带 `Authorization: Bearer`，token 存 `localStorage` 的 `access_token` |
| 信封解包 | `code === 0` 取 `data`，非 0 弹错误 |
| SSE | 不套信封，按 `type` 单独处理 |
| 上传 | 同步阻塞，用 loading 而非轮询 |
| CORS | 开发走 Vite 代理，同源无跨域；后端派生允许 `localhost:5173` |
| 页面刷新 | 路由守卫只看 `localStorage`，`/auth/me` 在需要时才拉 |

## 8. 待办

| 项 | 说明 |
| --- | --- |
| 注册页独立化 | 现在注册与登录合并在 `Login.vue`，后端 `/auth/register` 已就绪 |
| 来源卡片展开 | `sources` 已拿到，展示粒度可再细化到片段高亮 |
| 类型目录 | 目前类型散在 `api/` 与 `stores/` 内，未抽独立 `types/` |
