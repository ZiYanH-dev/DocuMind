# ===== AI 学习助手 · Makefile =====
# 底层调用: docker compose / uv / pnpm / ollama
# 启动方式：
#   make start   一键启动（Ollama 按需 → Docker → DB → 迁移 → 后端 → 前端）
#   make stop    停止后端和前端（保留 Docker + Ollama）
#   make help    查看所有可用命令

# ===== 基础配置 =====
BACKEND_DIR     := backend
FRONTEND_DIR    := frontend
LOGS_DIR        := var/logs
DOCKER_COMPOSE  := docker compose
UV              := uv
PNPM            := pnpm

# 端口 / 模型：单一事实来源 = 根目录 .env（缺省值兜底）
BACKEND_PORT    ?= 8000
FRONTEND_PORT   ?= 5173
EMBEDDING_MODEL ?= nomic-embed-text
-include .env

$(shell mkdir -p $(LOGS_DIR))

.PHONY: help
help:  ## 显示所有可用命令
	@echo ""
	@echo "📚 AI 学习助手 · 命令列表"
	@echo "============================"
	@echo "  make start         一键启动（Ollama → Docker → DB → 迁移 → 后端 → 前端）"
	@echo "  make stop          停止后端和前端（保留 Docker + Ollama）"
	@echo "  make stop-all      停止全部（后端 + 前端 + Ollama + Docker）"
	@echo "  make init          首次初始化（装依赖 + 迁移）"
	@echo "  make up            启动 PostgreSQL + Redis"
	@echo "  make down          停止并移除容器"
	@echo "  make db-migrate    执行 Alembic 升级到最新"
	@echo "  make be-dev        前台启动后端"
	@echo "  make fe-dev        前台启动前端"
	@echo "  make clean         清理临时文件"
	@echo "  make logs          查看 Docker 日志"
	@echo ""

# ===== 一键启动 =====
.PHONY: start stop stop-all

start: ensure-ollama ensure-docker up wait-postgres-ready db-migrate be-run fe-run  ## ⭐ 一键启动全部（Ctrl+C 无效，用 make stop 关）
	@echo ""
	@echo "=========================================="
	@echo "  ✅ 全部服务已启动"
	@echo "=========================================="
	@echo "  🐳  PostgreSQL : localhost:$(POSTGRES_PORT)"
	@echo "  🐳  Redis       : localhost:$(REDIS_PORT)"
	@echo "  🚀  后端 API    : http://localhost:$(BACKEND_PORT)"
	@echo "  📖  后端文档    : http://localhost:$(BACKEND_PORT)/docs"
	@echo "  🎨  前端页面    : http://localhost:$(FRONTEND_PORT)"
	@echo "  🛑  停止: make stop    📋 日志: tail -f $(LOGS_DIR)/backend.log"
	@echo "=========================================="

stop:  ## 🛑 停止后端和前端（保留 Docker + Ollama）
	@echo "🛑 停止后端和前端服务..."
	@pkill -f "uvicorn app.main" 2>/dev/null || true
	@pkill -f "vite" 2>/dev/null || true
	@echo "✅ 服务已停止（Docker 和 Ollama 仍在运行，全停: make stop-all）"

stop-all: stop ollama-down down  ## 停止全部（后端 + 前端 + Ollama + Docker）
	@echo "✅ 全部已停止"

# ===== Ollama 自检（按需：仅当 Embedding 指向本地 Ollama 时才检查）=====
.PHONY: ensure-ollama ollama-down ollama-status ollama-pull

ensure-ollama:
	@if ! echo "$(EMBEDDING_BASE_URL)" | grep -qE "localhost|127\.0\.0\.1"; then \
		echo "🦙 Embedding 使用云端服务（非 localhost），跳过 Ollama 检查"; \
	elif curl -sf http://127.0.0.1:11434 > /dev/null 2>&1; then \
		echo "   ✅ Ollama 服务已就绪 (port 11434)"; \
		if curl -sf http://127.0.0.1:11434/api/tags -o /tmp/.ollama_tags.json 2>/dev/null; then \
			if grep -q "$(EMBEDDING_MODEL)" /tmp/.ollama_tags.json 2>/dev/null; then \
				echo "   ✅ 模型 $(EMBEDDING_MODEL) 已就绪"; \
			else \
				echo "   ⚠️  模型 $(EMBEDDING_MODEL) 不存在（不自动 pull，请手动: ollama pull $(EMBEDDING_MODEL)）"; \
			fi; \
		fi; \
		rm -f /tmp/.ollama_tags.json; \
	else \
		echo "   🚀 Ollama 未运行，自动启动..."; \
		if [ "$$(uname)" = "Darwin" ] && open -Ra "Ollama" 2>/dev/null; then \
			open -a Ollama; \
		elif command -v ollama > /dev/null 2>&1; then \
			nohup ollama serve > $(LOGS_DIR)/ollama.log 2>&1 & \
		else \
			echo "   ❌ 未找到 ollama 命令，请手动启动 Ollama"; \
			exit 1; \
		fi; \
		ok=0; \
		for i in $$(seq 1 30); do \
			if curl -sf http://127.0.0.1:11434 > /dev/null 2>&1; then \
				echo "   ✅ Ollama 已就绪 (port 11434)"; \
				ok=1; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ "$$ok" != "1" ]; then \
			echo "   ❌ Ollama 启动超时（30s），请手动检查: ollama serve"; \
			exit 1; \
		fi; \
		if curl -sf http://127.0.0.1:11434/api/tags -o /tmp/.ollama_tags.json 2>/dev/null; then \
			if grep -q "$(EMBEDDING_MODEL)" /tmp/.ollama_tags.json 2>/dev/null; then \
				echo "   ✅ 模型 $(EMBEDDING_MODEL) 已就绪"; \
			else \
				echo "   ⚠️  模型 $(EMBEDDING_MODEL) 不存在（不自动 pull，请手动: ollama pull $(EMBEDDING_MODEL)）"; \
			fi; \
			rm -f /tmp/.ollama_tags.json; \
		fi; \
	fi

ollama-down:  ## 停止 Ollama 服务
	@pkill -f "ollama serve" 2>/dev/null || true
	@echo "✅ Ollama 已停止"

ollama-status:  ## 查看 Ollama 状态
	@echo "📊 Ollama 状态:"
	@if curl -s http://localhost:11434 > /dev/null 2>&1; then \
		echo "   服务: ✅ 运行中 (port 11434)"; \
	else \
		echo "   服务: ❌ 未运行"; \
	fi

ollama-pull:  ## 下载 Ollama 模型
	ollama pull $(EMBEDDING_MODEL)

# ===== Docker =====
.PHONY: ensure-docker up down restart ps logs wait-postgres-ready

ensure-docker:
	@echo "🐳 检查 Docker..."
	@if ! command -v docker > /dev/null 2>&1; then \
		echo "   ❌ docker 命令未找到，请先安装 Docker Desktop"; \
		exit 1; \
	fi
	@if docker info > /dev/null 2>&1; then \
		echo "   ✅ Docker 已就绪"; \
	elif [ "$$(uname)" = "Darwin" ] && open -Ra "Docker" 2>/dev/null; then \
		echo "   🚀 启动 Docker Desktop..."; \
		open -a Docker; \
		echo "   ⏳ 等待 Docker 就绪（首次启动约 30 秒）..."; \
		for i in $$(seq 1 60); do \
			if docker info > /dev/null 2>&1; then \
				echo "   ✅ Docker 已就绪"; \
				break; \
			fi; \
			sleep 2; \
		done; \
		if ! docker info > /dev/null 2>&1; then \
			echo "   ❌ Docker 启动超时，请手动检查"; \
			exit 1; \
		fi; \
	else \
		echo "   ❌ Docker daemon 未运行，请手动启动 Docker Desktop"; \
		exit 1; \
	fi

up: ensure-docker  ## 启动 PostgreSQL + Redis（后台）
	$(DOCKER_COMPOSE) up -d

down:  ## 停止并移除容器
	$(DOCKER_COMPOSE) down

restart: down up  ## 重启 Docker 服务

ps:  ## 查看容器状态
	$(DOCKER_COMPOSE) ps

logs:  ## 查看 Docker 日志
	$(DOCKER_COMPOSE) logs -f

wait-postgres-ready:
	@echo "🗄️  等待 PostgreSQL 就绪..."
	@ready=0; \
	for i in $$(seq 1 30); do \
		if $(DOCKER_COMPOSE) exec -T postgres pg_isready -U $(POSTGRES_USER) > /dev/null 2>&1; then \
			echo "   ✅ PostgreSQL 已就绪"; \
			ready=1; \
			break; \
		fi; \
		sleep 1; \
	done; \
	if [ "$$ready" != "1" ]; then \
		echo "   ❌ PostgreSQL 30 秒未就绪，请检查: docker compose logs postgres"; \
		exit 1; \
	fi

# ===== 后端 =====
.PHONY: be-install be-dev be-check be-shell be-run

be-install:  ## 安装后端依赖
	cd $(BACKEND_DIR) && $(UV) sync

be-dev:  ## 前台启动后端开发服务器
	cd $(BACKEND_DIR) && $(UV) run uvicorn app.main:app --reload --port $(BACKEND_PORT)

be-check:  ## 后端代码检查（ruff）
	cd $(BACKEND_DIR) && $(UV) run ruff check app/

be-shell:  ## 进入后端 Python 环境
	cd $(BACKEND_DIR) && $(UV) run python

be-run:  ## 后台启动后端（日志: logs/backend.log）
	@if lsof -ti :$(BACKEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "⏭️  后端已在运行 (port $(BACKEND_PORT))"; \
	else \
		cd $(BACKEND_DIR) && nohup $(UV) run uvicorn app.main:app --reload --port $(BACKEND_PORT) > ../$(LOGS_DIR)/backend.log 2>&1 & \
		echo "✅ 后端已启动 (port $(BACKEND_PORT))"; \
	fi

# ===== 数据库迁移 =====
.PHONY: db-migrate db-migrate-down db-migrate-create db-init

db-migrate:  ## 执行 Alembic 升级到最新
	cd $(BACKEND_DIR) && $(UV) run alembic upgrade head

db-migrate-down:  ## 回滚一个版本 (make db-migrate-down v=base 回滚全部)
	cd $(BACKEND_DIR) && $(UV) run alembic downgrade $(if $(v),$(v),-1)

db-migrate-create:  ## 创建新迁移 (make db-migrate-create msg="描述")
	@if [ -z "$(msg)" ]; then echo "❌ 用法: make db-migrate-create msg=\"描述\""; exit 1; fi
	cd $(BACKEND_DIR) && $(UV) run alembic revision --autogenerate -m "$(msg)"

db-init: up wait-postgres-ready db-migrate  ## 初始化数据库（迁移 + 建表）

# ===== 前端 =====
.PHONY: fe-install fe-dev fe-build fe-preview fe-run

fe-install:  ## 安装前端依赖
	cd $(FRONTEND_DIR) && $(PNPM) install

fe-dev:  ## 前台启动前端开发服务器
	cd $(FRONTEND_DIR) && $(PNPM) dev --port $(FRONTEND_PORT)

fe-build:  ## 构建生产版本
	cd $(FRONTEND_DIR) && $(PNPM) build

fe-preview:  ## 预览生产构建
	cd $(FRONTEND_DIR) && $(PNPM) preview

fe-run:  ## 后台启动前端（日志: logs/frontend.log）
	@if lsof -ti :$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "⏭️  前端已在运行 (port $(FRONTEND_PORT))"; \
	else \
		cd $(FRONTEND_DIR) && nohup $(PNPM) dev --port $(FRONTEND_PORT) > ../$(LOGS_DIR)/frontend.log 2>&1 & \
		echo "✅ 前端已启动 (port $(FRONTEND_PORT))"; \
	fi

# ===== 工具 =====
.PHONY: clean lint init

clean:  ## 清理临时文件
	@echo "🧹 清理临时文件..."
	@find $(BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
	@find $(BACKEND_DIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find $(BACKEND_DIR) -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	@rm -f $(LOGS_DIR)/*.log 2>/dev/null || true
	@echo "✅ 清理完成"

lint: be-check  ## 运行代码检查

init: be-install fe-install up wait-postgres-ready db-migrate  ## 首次初始化（装依赖 + 迁移）
