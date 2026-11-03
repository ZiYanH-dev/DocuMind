# 数据库表设计

> 数据库：PostgreSQL 17 + pgvector 扩展，镜像 `pgvector/pgvector:pg17`，宿主端口 5433
> 迁移文件：`backend/alembic/versions/` 下 `0001_initial_migration.py` 建表，`0002_alter_embedding_dim.py` 把向量维度从 1536 改为 768

## 1. 实体关系（ER）

```
users (1) ───< (N) documents (1) ───< (N) document_chunks
  │
  └──────────< (N) conversations (1) ───< (N) messages
```

- 一个用户拥有多份文档、多个会话。
- 一份文档拆分为多个分块（`document_chunks`），分块携带向量 `embedding`。
- 一个会话包含多条消息（user / assistant 交替）。
- 检索时通过 `document_chunks → documents.user_id` 关联，将分块限定在**当前用户**范围内。

## 2. 表结构

### 2.1 users（用户）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT | PK, 自增 | 用户 ID |
| username | VARCHAR(50) | NOT NULL, UNIQUE | 用户名（登录名） |
| email | VARCHAR(255) | UNIQUE, NULL | 邮箱（可选） |
| hashed_password | VARCHAR(255) | NOT NULL | bcrypt 哈希密码 |
| is_active | BOOLEAN | NOT NULL, DEFAULT true | 是否启用 |
| created_at | TIMESTAMPTZ | NOT NULL, 默认 now() | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL, 默认 now(), 更新时刷新 | 更新时间 |

索引：
- `ix_users_username`、`ix_users_email`。

### 2.2 documents（文档）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT | PK, 自增 | 文档 ID |
| user_id | BIGINT | FK→users.id ON DELETE CASCADE, NOT NULL, INDEX | 归属用户 |
| title | VARCHAR(255) | NOT NULL | 标题（默认取文件名去扩展名） |
| file_name | VARCHAR(255) | NOT NULL | 原始文件名 |
| file_path | VARCHAR(500) | NOT NULL | 服务器落盘路径 `{user_id}_{8位随机段}_{file_name}` |
| file_size | BIGINT | NOT NULL | 字节数 |
| file_type | VARCHAR(50) | NOT NULL | `pdf` / `docx` / `txt` |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'processing' | 处理状态（见下） |
| error_message | TEXT | NULL | 处理失败原因 |
| created_at | TIMESTAMPTZ | NOT NULL, 默认 now() | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL, 默认 now(), 更新时刷新 | 更新时间 |

`status` 取值：
- `processing`（处理中） / `completed`（完成） / `failed`（失败）。
索引：
- `ix_documents_user_id`。

### 2.3 document_chunks（文档分块 / 向量）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT | PK, 自增 | 分块 ID |
| document_id | BIGINT | FK→documents.id ON DELETE CASCADE, NOT NULL, INDEX | 所属文档 |
| chunk_index | INTEGER | NOT NULL | 分块序号 |
| content | TEXT | NOT NULL | 分块文本 |
| embedding | VECTOR(768) | NULL | 文本向量，维度必须与 `settings.embedding_dim` 一致 |
| created_at | TIMESTAMPTZ | NOT NULL, 默认 now() | 创建时间 |

索引：
- `ix_document_chunks_document_id`；
- 向量索引 `ix_document_chunks_embedding`（IVFFlat，`vector_cosine_ops`，`lists=100`）。
级联：
- `documents` 删除时本表随 `ON DELETE CASCADE` 一并删除。

> 分块参数：`chunk_size=800`、`chunk_overlap=100`，配置在 `backend/app/config/app.yaml` 的 `parser` 段。
> 落盘名带 8 位随机段，是为了同名文件重复上传时各占一个文件，删除其中一条不会连带删掉另一条的源文件。

### 2.4 conversations（会话）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT | PK, 自增 | 会话 ID |
| user_id | BIGINT | FK→users.id ON DELETE CASCADE, NOT NULL, INDEX | 归属用户 |
| title | VARCHAR(255) | NOT NULL | 会话标题 |
| created_at | TIMESTAMPTZ | NOT NULL, 默认 now() | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL, 默认 now(), 更新时刷新 | 更新时间 |

索引：
- `ix_conversations_user_id`。

### 2.5 messages（消息）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT | PK, 自增 | 消息 ID |
| conversation_id | BIGINT | FK→conversations.id ON DELETE CASCADE, NOT NULL, INDEX | 所属会话 |
| role | VARCHAR(20) | NOT NULL | `user` / `assistant` |
| content | TEXT | NOT NULL | 消息正文 |
| sources | JSONB | NULL | 引用来源（数组，结构见 `SourceInfo`） |
| created_at | TIMESTAMPTZ | NOT NULL, 默认 now() | 创建时间 |

索引：
- `ix_messages_conversation_id`。
- 级联：`conversations` 删除时消息一并删除。

## 3. 向量检索在表层面的约束

- 使用 pgvector `<=>` 算子计算**余弦距离**，再取 `1 - 距离` 作为相似度 `score`。
- 检索 SQL 在 `ChunkRepository.vector_search`：
	- `JOIN documents` 后 `WHERE documents.user_id = :user_id`，保证只检索当前用户的文档；
	- 相似度阈值在 SQL 层过滤，不通过的片段不进结果集；
	- 按距离升序取前 `vector_recall_k` 条，不是最终条数。
- 这一路只是检索的其中一路，融合与重排见 [ai/retrieval.md](./ai/retrieval.md)。
- 向量维度必须与 `settings.embedding_dim` 一致，默认 768，配置在 `app.yaml` 的 `embedding.dim`。
维度与列定义不一致时插入直接报错。
- 换 embedding 模型要重算全部存量向量，否则新旧向量不可比。
pgvector 不支持直接改列维度，需要像 `0002` 那样用 `USING embedding::vector(N)` 重建列。

## 4. 级联删除一览

| 父表 | 子表 | 行为 |
| --- | --- | --- |
| users | documents | CASCADE |
| users | conversations | CASCADE |
| documents | document_chunks | CASCADE |
| conversations | messages | CASCADE |

删除文档只删记录不够：源文件与三类缓存也要一起清理，见 [ai/indexing.md](./ai/indexing.md) 第 5 节。
