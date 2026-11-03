# 后端配置体系

> 代码：`backend/app/config/settings.py`、`backend/app/config/app.yaml`、项目根 `.env`。
> 启动流程见 [../ops/getting-started.md](../ops/getting-started.md)。

## 1. 三段式分工

配置按「是否机密」「是否进 git」两个维度分三段，边界不允许混。

| 段 | 文件 | 内容 | 进 git | 谁读 |
| --- | --- | --- | --- | --- |
| 机密与接入 | 项目根 `.env` | `SECRET_KEY`、数据库密码、Redis 端口、`LLM_*`、`EMBEDDING_*` | 否，`.gitignore` 排除 | `Settings` |
| 超参 | `backend/app/config/app.yaml` | 温度、`max_tokens`、检索各路的 k 与开关、分块大小 | 是 | `load_ai_config()` |
| 默认值 | `Settings` 类体 | 兜底值，多数直接取 YAML 里的键 | 是 | — |

YAML 只放非机密超参，不放任何连接地址、模型名与 Key。
理由：超参要随代码评审一起改、要能回滚，放进 YAML 才有版本历史；Key 与地址按环境不同，放 `.env`。

## 2. 加载顺序

```
import settings.py
  ├─ load_ai_config()        读 app.yaml，启动即 fail-fast，缺文件直接报错
  ├─ Settings() 实例化       字段默认值从 _AI 取值
  │    └─ 优先级：进程环境变量 > 根 .env > 类体默认值(来自 YAML)
  ├─ field_validator         把 upload_dir / log_dir 解析成绝对路径并建目录
  └─ settings = get_settings()
       └─ get_settings() 带 lru_cache，全进程只实例化一次
```

`Settings` 的关键配置项：

| 配置 | 值 | 影响 |
| --- | --- | --- |
| `env_file` | `REPO_ROOT / ".env"` | 只认项目根 `.env`，`backend/.env` 永远不会被读 |
| `frozen` | `True` | 实例化后只读，业务代码改不动配置 |
| `extra` | `ignore` | 多写的变量被静默丢弃 |
| `case_sensitive` | 默认 `False` | `.env` 里写 `llm_api_key` 或 `LLM_API_KEY` 都认 |

`extra="ignore"` 的代价：`.env` 里写错的键不会报错，只会被丢掉。
因此 `.env` 必须从 `.env.example` 复制，不要手写。

## 3. 分字段推导连接串

数据库与 Redis 都不写完整 URL，而是分字段给出，再由属性拼接：

| 属性 | 由哪些字段拼 | 结果 |
| --- | --- | --- |
| `resolved_database_url` | `postgres_user`、`postgres_password`、`postgres_host`、`postgres_port`、`postgres_db` | `postgresql+psycopg2://...` |
| `resolved_redis_url` | `redis_host`、`redis_port`、`redis_db` | `redis://...` |

好处是测试里只要覆盖 `POSTGRES_DB` 一个变量就能指向测试库，不用拼整条 URL。
反例是旧写法 `DATABASE_URL`：因为 `extra="ignore"`，写了也无效且不报错。

## 4. 缺省复用规则

Embedding 与重排都可以不单独配，缺省复用 LLM 的凭据。

| 用途 | 派生属性 | 复用逻辑 |
| --- | --- | --- |
| Embedding Key | `effective_embedding_api_key` | `embedding_api_key or llm_api_key` |
| Embedding 基址 | `effective_embedding_base_url` | `embedding_base_url or llm_base_url` |
| 重排 Key | `effective_rerank_api_key` | `rerank_api_key or llm_api_key` |
| 重排地址 | `rerank_endpoint` | 取 `llm_base_url` 的 scheme 与 host，拼 `RERANK_PATH` |

典型部署是 LLM 用云端、Embedding 用本地 Ollama，两个基址不同，此时必须显式填 `EMBEDDING_BASE_URL`。
重排是百炼原生接口，不在 OpenAI 兼容协议内，因此路径写死在 `RERANK_PATH`，只复用主机与 Key。

## 5. CORS 派生

`cors_origins` 留空时，`cors_origins_list` 由 `frontend_port` 派生：

```
http://localhost:{frontend_port}
http://127.0.0.1:{frontend_port}
```

需要额外域名时在 `.env` 写 `CORS_ORIGINS`，逗号分隔，此时派生逻辑不再生效。

## 6. 路径解析

`upload_dir` 与 `log_dir` 由 `field_validator` 处理：
- 相对路径按 `backend/` 解析为绝对路径；
- 目录不存在时在实例化阶段创建。

因此这两个配置写相对路径也不会因工作目录不同而跑偏。

## 7. 单例客户端

`config/` 下的客户端都在模块导入时实例化一次：

| 实例 | 文件 | 说明 |
| --- | --- | --- |
| `settings` | `settings.py` | `lru_cache` 包一层 |
| `engine`、`SessionLocal` | `database.py` | `pool_pre_ping=True`，SQL echo 跟随 `app_debug` |
| `redis_client` | `redis.py` | `decode_responses=True` |
| `llm_service` | `llm_client.py` | `ChatOpenAI`，`streaming=True` |
| `embedding_service` | `embedding_client.py` | `OpenAIEmbeddings`，关掉 `check_embedding_ctx_length` |

## 8. 边界与注意事项

| 项 | 说明 |
| --- | --- |
| 必须在导入 `app.*` 之前设环境变量 | `settings` 在模块导入时就实例化并被 `lru_cache` 缓存，导入后再改无效，测试的 `conftest.py` 因此把 `os.environ` 放在最前面 |
| 只用 Settings 真实存在的键 | 分字段推导加 `extra="ignore"`，写错键名不报错 |
| YAML 缺文件即崩溃 | 这是有意设计，宁可启动失败也不要带着空配置跑起来 |
| 改配置要重启 | `frozen=True` 加单例，热更新不支持 |
