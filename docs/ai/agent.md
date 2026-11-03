# Agent 设计与组装

> 代码：`backend/app/agent/agent.py`（组装）、`backend/app/agent/tools.py`（工具）。
> 检索实现见 [retrieval.md](./retrieval.md)，事件推流见 [../04-api.md](../04-api.md) 第 6 节。

## 1. 它是什么

Agent 是一个 LangGraph 编译后的状态图，由 `langchain.agents.create_agent` 生成。
图内两个节点：`model` 负责 LLM 推理，`tools` 负责执行工具。
LLM 每轮输出若带 `tool_calls`，控制流进 `tools` 节点，工具结果作为 `ToolMessage` 回到 `model`。
没有 `tool_calls` 时图直接结束，该轮的 token 就是最终回答。

这是 Agentic RAG 与固定 RAG 的区别：
- 固定 RAG 每次请求都先检索再生成，无法跳过；
- Agentic RAG 让 LLM 自己判断要不要检索，打招呼与闲聊不会触发检索。

## 2. 组成

| 部件 | 位置 | 内容 |
| --- | --- | --- |
| System Prompt | `agent.py` `SYSTEM_PROMPT` | 五条行为准则，规定何时调工具、何时直答 |
| LLM | `config/llm_client.py` `llm_service.llm` | `ChatOpenAI`，`streaming=True`，温度 0.7，`max_tokens` 2048 |
| 工具 | `agent.py` `build_tools()` | `search_knowledge`、`list_documents` |
| 返回值 | `agent.py` `ChatAgentBundle` | `agent` 图实例 + `retrieved_hits` 命中收集器 |

System Prompt 的五条准则：

1. 打招呼、闲聊、自我介绍不调工具，直接回答。
2. 知识类提问必须先调 `search_knowledge`，检索不到再按通用知识回答。
3. 用户提到"我的文档""我的知识库"时先调 `list_documents`。
4. 回答要简洁有条理，并标注引用来源。
5. 用户没有上传任何文档时如实告知。

## 3. 两个工具

| 工具 | 入参 | 行为 | 返回 |
| --- | --- | --- | --- |
| `search_knowledge` | `query: str`、`top_k: int` 默认跟随配置 | 调 `retrieval.pipeline.retrieve()`，把命中写进收集器，再拼成模型可读文本 | 每段为 `[来源: 标题, 相关度: 0.82]` 加正文，段间空行 |
| `list_documents` | 无 | 调 `DocumentRepository.list_by_user_id()`，逐条带分块数 | 文档标题、ID、状态、分块数的列表文本 |

工具用闭包捕获当前请求的 `session` 与 `user_id`。
因此检索天然按用户隔离，不需要在查询里额外传用户参数。

`hits` 收集器由 `create_chat_agent` 创建并传入 `build_tools`。
`search_knowledge` 每次命中都追加 `SourceInfo`，服务层据此生成带 `document_id` 与 `chunk_index` 的精确引用。
不从回答文本里正则提取来源，因为模型会改写引用格式，文本解析不可靠。

## 4. 怎么用

一次请求构建一次，不复用：

```python
bundle: ChatAgentBundle = create_chat_agent(self._db, user.id)
messages = build_initial_messages(chat_in.content, history)

for mode, event in bundle.agent.stream(
    {"messages": messages},
    stream_mode=["updates", "messages"],
):
    ...
sources = self._dedup_sources(bundle.retrieved_hits)
```

`stream_mode` 同时开两路：

| mode | 用途 | 取什么 |
| --- | --- | --- |
| `updates` | 观察图节点产出 | `tools` 节点里的 `ToolMessage`，取出工具名写链路日志 |
| `messages` | 拿 token 流 | 只取 `langgraph_node == "model"` 且非 `tool_calls` 的 `AIMessageChunk` |

## 5. 边界与注意事项

| 项 | 说明 |
| --- | --- |
| 每次请求新建 | 工具闭包绑定了 `Session`，跨请求复用会把上一个会话的数据库连接带到新请求 |
| token 必须按节点过滤 | 工具内部的 LLM 调用（如查询改写）同样产生 `messages` 事件，不过滤会把中间产物当回答推给前端 |
| 工具内部吞异常 | `search_knowledge` 捕获异常后返回错误字符串，不向外抛，避免整图中断导致本轮回答为空 |
| 检索次数不确定 | 模型可能一次都不调，也可能多轮调用，`retrieved_hits` 按去重后顺序输出，不做数量假设 |
| 无 token 兜底 | 流结束时若 `answer_parts` 为空，服务层只记 warning，不补文案 |

## 6. 可扩展点

- 新增工具写在 `build_tools()` 内，用 `@tool` 装饰并写清 `Args`，模型靠 docstring 判断何时调用。
- 新增工具若要参与引用，把命中追加进 `hit_collector`，服务层自动去重输出。
- 换 provider 只改 `.env` 的 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`，`ChatOpenAI` 走 OpenAI 兼容协议，代码不动。
