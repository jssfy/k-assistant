.PHONY: help setup db-init up down dev dev-api dev-web kill kill-all test psql logs

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# === 初始化 ===

setup: ## 首次安装：依赖 + 数据库 + 前端
	uv sync
	pnpm --dir web install
	docker compose up -d
	@echo "等待 PostgreSQL 就绪..."
	@sleep 5
	uv run alembic upgrade head
	PYTHONPATH=. uv run python scripts/seed.py
	@echo "✅ 初始化完成，运行 make dev 启动开发服务"

db-init: ## 数据库迁移 + 种子数据
	uv run alembic upgrade head
	PYTHONPATH=. uv run python scripts/seed.py

# === Docker 服务 ===

up: ## 启动 postgres + litellm
	docker compose up -d

down: ## 停止 Docker 服务
	docker compose down

# === 开发 ===

dev: up ## 启动全部（Docker + 后端 + 前端）
	@cleanup() { \
		echo ""; echo "Stopping..."; \
		kill $$API_PID $$WEB_PID 2>/dev/null; \
		wait $$API_PID $$WEB_PID 2>/dev/null; \
		lsof -ti :8000 | xargs kill 2>/dev/null; \
		lsof -ti :5173 | xargs kill 2>/dev/null; \
		echo "All stopped"; \
	}; \
	trap cleanup INT TERM EXIT; \
	uv run uvicorn app.main:app --reload --port 8000 & API_PID=$$!; \
	pnpm --dir web dev & WEB_PID=$$!; \
	wait

dev-api: up ## 仅启动后端
	uv run uvicorn app.main:app --reload --port 8000

dev-web: ## 仅启动前端
	pnpm --dir web dev

kill: ## 停止本地前后端进程
	@lsof -ti :8000 | xargs kill 2>/dev/null && echo "Backend stopped" || echo "Backend not running"
	@lsof -ti :5173 | xargs kill 2>/dev/null && echo "Frontend stopped" || echo "Frontend not running"

kill-all: down kill ## 停止全部（Docker + 本地进程）

# === 工具 ===

test: ## 运行测试
	uv run pytest -v

psql: ## 进入数据库终端
	docker compose exec postgres psql -U postgres -d k_assistant

logs: ## 查看 Docker 日志
	docker compose logs -f --tail=50
