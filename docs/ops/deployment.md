# 生产部署指南

> 用 Docker 构建整个全栈并以 nginx 统一对外。
> 一条命令起全栈：`docker compose -f docker-compose.prod.yml up -d --build`
> 本地开发启动见 [getting-started.md](./getting-started.md)。

## 1. 架构总览

```
        ┌───────────── 公网 (PROD_PORT:80) ─────────────┐
        ▼                                               │
┌───────────────┐   /api/* 反代   ┌─────────────────┐
│   frontend    │ ──────────────> │     backend      │
│   (nginx)     │                 │  (uvicorn:8000)  │
│  / 静态资源   │                 │  FastAPI 应用     │
└───────────────┘                 └────┬────────┬────┘
                                       │        │
                              ┌────────▼──┐  ┌──▼───────┐
                              │ PostgreSQL│  │  Redis   │
                              │ (pgvector)│  │          │
                              └───────────┘  └──────────┘
```

| 服务 | 镜像 | 对外 | 责任 |
| --- | --- | --- | --- |
| frontend | nginx + Vite build | 80（nginx） | 托管静态资源、SPA 路由、`/api` 反代 |
| backend | uv + uvicorn | 仅内网 expose:8000 | API、迁移（启动时自动跑） |
| postgres | pgvector:pg17 | 内网 | 主库 + 向量检索 |
| redis | redis:6-alpine | 内网 | 会话/缓存 |

> 生产**只暴露** nginx 的 80 端口。后端、PostgreSQL、Redis 都在 compose 内网，不对外。

## 2. 生产涉及的文件

| 文件 | 作用 |
| --- | --- |
| `docker-compose.prod.yml` | 生产编排（四服务） |
| `backend/Dockerfile` | 后端多阶段镜像（uv 装依赖 → 运行） |
| `frontend/Dockerfile` | 前端多阶段镜像（node 构建 → nginx） |
| `frontend/nginx.conf` | nginx 配置：SPA 回退 + `/api` 反代 + SSE 透传 |
| `.env`（根目录） | 全部密钥与接入配置 |

## 3. 部署步骤

### 3.1 准备 `.env`

生产 `.env` 需要有（用 `:?` 强制校验的会报错）：

```bash
# 必填
SECRET_KEY=<强随机串>       # 必须改，不能默认
LLM_API_KEY=<你的 Key>
LLM_BASE_URL=https://.../v1
LLM_MODEL=qwen-max

# 可选（有默认值兜底）
POSTGRES_USER=documind
POSTGRES_PASSWORD=<强密码>
POSTGRES_DB=documind
EMBEDDING_BASE_URL=...      # 如本地 Embedding 换公网可访问地址
EMBEDDING_MODEL=nomic-embed-text
PROD_PORT=80                # 对外端口，如 80 被占改 8080
```

### 3.2 构建并启动

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

启动顺序由 `depends_on: condition: service_healthy` 保证：
`postgres` / `redis` 健康 → 起 backend（先 `alembic upgrade head` 再 uvicorn）→ 起 frontend。

### 3.3 验证

```bash
docker compose -f docker-compose.prod.yml ps
# 前端
curl -o /dev/null -w '%{http_code}\n' http://localhost:80          # 200
# 后端健康检查（经 nginx 反代）
curl -o /dev/null -w '%{http_code}\n' http://localhost/api/v1/... # 200
# 后端直达（进容器）
docker compose -f docker-compose.prod.yml exec backend curl -s localhost:8000/health
# 日志
docker compose -f docker-compose.prod.yml logs -f backend
```

## 4. 数据库迁移

迁移在 **backend 容器启动时自动执行**（Dockerfile CMD：
- `alembic upgrade head && uvicorn ...`），无需手动干预。

手动操作（手动跑迁移 / 回滚）：

```bash
# 进到 backend 运行
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend alembic downgrade -1
```

## 5. 数据持久化

| 卷 | 挂载点 | 内容 | 删除即清空 |
| --- | --- | --- | --- |
| `postgres_data_prod` | `/var/lib/postgresql/data` | 数据库 | `down -v` |
| `redis_data_prod` | `/data` | Redis 数据 | `down -v` |
| `uploads_prod` | `/app/var/uploads` | 用户上传文件 | `down -v` |

> `docker compose down` 不删卷（数据保留）；`docker compose down -v` 才删（⚠️ 清空全部数据）。

## 6. 更新与回滚

```bash
# 更新（改代码后重建镜像）
docker compose -f docker-compose.prod.yml up -d --build backend frontend

# 全部停止（保留数据）
docker compose -f docker-compose.prod.yml down

# 彻底清理（含数据卷）
docker compose -f docker-compose.prod.yml down -v
```

## 7. 上线到服务器（简要）

```bash
# 1. 服务器装 Docker
# 2. 代码拉到服务器
git clone <repo-url> && cd documind   # 目录名 = GitHub 仓库名
# 3. 放生产 .env
cp .env.example .env && vim .env   # 填生产密钥
# 4. 构建启动
docker compose -f docker-compose.prod.yml up -d --build
# 5. 公网访问（二选一）
#    a. 服务器有公网 IP/已备案 → 云厂商安全组放行 PROD_PORT
#    b. 本机/临时演示 → 内网穿透，如 cloudflared tunnel / frp 映射到 localhost:PROD_PORT
```

## 8. 待办（后续可补）

- [ ] CI/CD：
	- GitHub Actions 自动构建镜像 + 部署到服务器
- [ ] TLS：
	- nginx 挂证书（HTTPS）+ /api 走 wss
- [ ] 健康检查：
	- 增加 backend `/health` 到 `healthcheck`
- [ ] 上传后门：
	- `UPLOAD_DIR` 卷定期备份
- [ ] 日志汇集：
	- docker 日志接入集中式日志（如 Loki / ELK）