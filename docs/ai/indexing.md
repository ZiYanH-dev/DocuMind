# 文档索引与缓存

> 代码：`backend/app/utils/document_parser.py`、`config/embedding_client.py`、`service/document_service.py`、`core/cache.py`。
> 表结构见 [../03-database-design.md](../03-database-design.md)，检索消费方式见 [retrieval.md](./retrieval.md)。

## 1. 它是什么

索引是把一份文件变成可检索分块的同步流程，在上传请求内完成。
流程为解析 → 分块 → 向量化 → 入库，四步都在同一个请求里跑完，没有后台任务队列。

## 2. 解析

| 文件类型   | 库             | 做法                                                                   |
| ------ | ------------- | -------------------------------------------------------------------- |
| `pdf`  | `pypdf`       | 逐页 `extract_text()`，页间用空行拼接                                          |
| `docx` | `python-docx` | 取非空段落文本，段间用空行拼接                                                      |
| `txt`  | 内置解码          | 依次试 `utf-8`、`gbk`、`gb18030`、`big5`，全失败用 `utf-8` 带 `errors="replace"` |

允许上传的类型为 `pdf`、`docx`、`txt`，`doc` 在解析器里也支持，但不在上传白名单内。

## 3. 分块

用 `RecursiveCharacterTextSplitter`，按分隔符优先级递归切分：

```
["\n\n", "\n", "。", "；", "，", " ", ""]
```

| 参数 | 值 | 位置 |
| --- | --- | --- |
| `chunk_size` | 800 | `config/app.yaml` `parser.chunk_size` |
| `chunk_overlap` | 100 | `config/app.yaml` `parser.chunk_overlap` |

分隔符按中文标点优先，避免在句子中间截断。
切完对每块 `strip()`，空块丢弃，块序号从 0 连续编号。

## 4. 向量化与入库

| 项 | 值 |
| --- | --- |
| 客户端 | `OpenAIEmbeddings`，`check_embedding_ctx_length=False` |
| 维度 | 768，`config/app.yaml` `embedding.dim` |
| 列类型 | `Vector(settings.embedding_dim)` |
| 索引 | IVFFlat，`vector_cosine_ops`，`lists=100` |
| Key 与基址 | 缺省复用 LLM 的，可用 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL` 单独覆盖 |

所有分块一次性批量送 embedding 接口，返回后逐条构造成 `DocumentChunk` 写入。
写入完成后文档状态由 `processing` 改为 `completed`。

## 5. 三级缓存与失效

| 命名空间 | 内容 | TTL | 失效时机 |
| --- | --- | --- | --- |
| `documind:history:{conv_id}` | 会话最近 10 条消息 | 600 秒 | 每轮问答后回写覆盖 |
| `documind:retrieval:{user_id}:{sha1}` | 检索结果 | 300 秒 | 文档增删时按用户前缀清空 |
| `documind:document:list:{user_id}:{skip}:{limit}` | 文档列表分页结果 | 120 秒 | 文档增删时按用户前缀清空 |
| 进程内 `_cache[user_id]` | BM25 索引与语料 | 无 TTL | 文档增删时显式 `invalidate(user_id)` |

上传成功与删除文档都调用 `DocumentService._invalidate_user`，一次清掉上述后三项。
BM25 索引不在 Redis 里，必须显式失效，否则会继续用旧语料打分。

Redis 不可用时全部读写静默降级：读返回 `None`，写与删除直接跳过。
缓存故障不会让主链路失败，只是退化为每次都查库。

## 6. 换 embedding 模型的代价

向量维度写死在列类型里，换模型必须同时做三件事：

1. 改 `config/app.yaml` 的 `embedding.dim`。
2. 新增一个类似 `0002_alter_embedding_dim` 的迁移，重建列。pgvector 不支持直接 `ALTER` 维度，要用 `USING embedding::vector(N)` 转换。
3. 重算全部存量分块向量，否则新旧向量不可比，检索结果会失真。

## 7. 边界与注意事项

| 项 | 说明 |
| --- | --- |
| 同步阻塞 | 上传请求要等向量化完成，大文件下这是主要耗时点，也是当前最明显的优化位 |
| 一次性批量送向量 | 不按批切分，超长文档会形成很大的单次请求 |
| 落盘名带随机段 | `{user_id}_{8 位随机}_{文件名}`，同名文件互不覆盖，删除一条不会连带删掉另一条的源文件 |
| 失败保留记录 | 解析或向量化失败时文档留在库中，`status=failed`，`error_message` 记录原因 |
| 分块与语料指纹不一致 | 指纹取 `count:min_id:max_id`，只判断语料是否变化，不校验正文改动 |
| 全量读分块 | `list_all_by_user` 只在 BM25 索引未命中时调用，命中后不产生全量读取 |
