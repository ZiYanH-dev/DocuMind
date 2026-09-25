# ===== Python 运行镜像（复用本地 python:3.11-slim）=====
# 多阶段构建：installer 装依赖 → runner 运行

FROM python:3.11-slim AS base
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# 安装 uv（pip 官方安装方式，体积远小于专用 uv 镜像）
RUN pip install --no-cache-dir uv

# ===== 依赖缓存层（依赖不变则此层缓存复用）=====
FROM base AS dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ===== 运行镜像 =====
FROM base AS runner
COPY --from=dependencies /app/.venv /app/.venv
# 拷贝业务代码（app 包）
COPY app/ app/
COPY alembic.ini ./
COPY alembic/ alembic/
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 启动前先自动执行数据库迁移，再启动 uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]