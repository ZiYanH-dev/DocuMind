# 后端测试结构

> 代码：`backend/tests/`，替身集中在 `tests/fakes.py`，夹具在 `tests/conftest.py`。
> 质量门禁命令见 [../02-architecture.md](../02-architecture.md) 第 6 节。

## 1. 四层测试

目录决定分层，`conftest.pytest_collection_modifyitems` 按目录自动打 marker，不用在文件里手写标记。

| 层 | 目录 | 依赖 | 用真实数据库 | 跑法 |
| --- | --- | --- | --- | --- |
| `unit` | `tests/unit/` | 无 | 否 | `pytest -m unit` |
| `service` | `tests/service/` | 无，用内存替身 | 否 | `pytest -m service` |
| `http` | `tests/http/` | 无，TestClient + 替身 | 否 | `pytest -m http` |
| `integration` | `tests/integration/` | 真实 PostgreSQL | 是 | `pytest -m integration` |

前三层在没装 Docker 的机器上也能全量跑通。
`integration` 层连不上库时是 skip 而不是 error，避免整批测试因为环境缺失变成红色。

## 2. 各层测什么

| 层 | 覆盖对象 | 代表文件 |
| --- | --- | --- |
| `unit` | 纯函数与算法，含分层约束 | `test_fusion.py`、`test_keyword.py`、`test_rerank.py`、`test_rewrite.py`、`test_parser.py`、`test_pipeline.py`、`test_cache.py`、`test_security.py`、`test_tools.py`、`test_layering.py` |
| `service` | 四个 service 的业务分支 | `test_auth_service.py`、`test_document_service.py`、`test_conversation_service.py`、`test_chat_service.py` |
| `http` | 路由、鉴权、信封结构、错误码 | `test_auth_api.py`、`test_documents_api.py`、`test_conversations_api.py`、`test_chat_api.py`、`test_error_handling.py` |
| `integration` | 经 HTTP 走完整链路，含 SSE 流 | `test_main_flow.py`、`test_chat_stream.py` |

`test_layering.py` 属于特殊用例：它用 AST 静态解析源码，不执行被测算代码，因此不依赖数据库与网络。

## 3. 替身清单

`tests/fakes.py` 提供九类替身，全部不碰网络与真实 LLM。

| 替身 | 替代对象 | 要点 |
| --- | --- | --- |
| `FakeSession` | `sqlalchemy.orm.Session` | 只记录 `add`、`commit`、`rollback` 调用 |
| `FakeCache` | `core.cache.RedisCache` | 内存字典，可断言命中与失效 |
| `MemoryStore` | 整个持久层 | 一个用例内共享的字典，`reset_store()` 每用例重置 |
| `FakeUserRepository` | `UserRepository` | 走 `MemoryStore` |
| `FakeConversationRepository` | `ConversationRepository` | 走 `MemoryStore` |
| `FakeMessageRepository` | `MessageRepository` | 走 `MemoryStore` |
| `FakeDocumentRepository` | `DocumentRepository` | 走 `MemoryStore`，含分块计数 |
| `FakeChunkRepository` | `ChunkRepository` | 走 `MemoryStore`，可预置向量检索结果 |
| `RecordingGraph` | `CompiledStateGraph` | 与 `stream` 同名同签名，回放预置事件并记录入参 |

`RecordingGraph` 是关键：它回放的是真实的 `(stream_mode, event)` 事件对。
因此 `chat_service` 里按 `langgraph_node` 过滤 token 的分支能被真实覆盖，不需要起 LLM。

构造事件的三个辅助函数：

| 函数 | 用途 |
| --- | --- |
| `token_event(text, node="model")` | 造 `messages` 事件，可指定节点名验证过滤逻辑 |
| `tool_update_event(*names)` | 造 `updates` 事件，带 `ToolMessage` |
| `make_source(document_id, chunk_index)` | 造一条 `SourceInfo` 命中 |

## 4. 关键夹具

| 夹具 | 作用域 | 说明 |
| --- | --- | --- |
| `_stub_embeddings` | 每用例自动 | 把 `embed_texts`、`embed_query` 替成返回零向量，维度取 `settings.embedding_dim` |
| `_prepare_db` | session | 建 `vector` 扩展与全部表，结束后 `drop_all`；连不上库则整批 skip |
| `db_session` | 每用例 | 独立事务，结束回滚，用例之间不污染 |
| `client` | 每用例 | TestClient，覆盖 `get_db` 复用测试事务 |
| `_reset_fake_store` | 每用例自动 | 清空内存替身 |
| `fake_repositories` | 每用例 | 把所有 Repository 换成内存替身 |
| `alice`、`bob` | 每用例 | 两个隔离用户，用来验证按用户隔离 |
| `auth_headers` | 每用例 | 已登录用户的 Bearer 头 |
| `upload_dir` | 每用例 | 指向 `tmp_path`，不写真实 `var/uploads` |

Embedding 替身的维度取 `settings.embedding_dim` 而不是写死数字。
原因：迁移把列维度从 1536 改成 768 后，写死的旧值会让入库直接失败。

## 5. 环境变量先于导入

`conftest.py` 第一段代码设 `os.environ`，之后才 import `app.*`：

```python
os.environ.setdefault("POSTGRES_DB", "documind_test")
os.environ.setdefault("REDIS_DB", "1")
```

顺序不能颠倒。
`Settings` 在模块导入时就实例化并被 `lru_cache` 缓存，导入之后再改环境变量不会生效。
测试库固定为 `documind_test`，绝不指向开发库。

## 6. 端到端验证

`make e2e` 跑 `backend/scripts/http_e2e.py`，对已经启动的服务发真实 HTTP 请求。
它与 `integration` 层的区别：`integration` 用 TestClient 在进程内调用，`e2e` 打真实端口，覆盖中间件、CORS 与 SSE 的实际帧格式。

## 7. 边界与注意事项

| 项 | 说明 |
| --- | --- |
| 上传接口在集成测试里会调 Embedding | 靠 `_stub_embeddings` 全局替身挡住，不需要真实 Key |
| `integration` 需要先建库 | 先跑 `make db-init`，再跑全量测试 |
| 分层测试失败优先级最高 | 它守护依赖方向，失败说明架构被破坏，先修它再看业务用例 |
| xfail 用 `strict=True` | 修好债务后测试会报 XPASS 失败，逼着摘掉标记 |
