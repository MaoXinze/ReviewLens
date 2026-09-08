# ReviewLens 常用命令快捷方式
PY ?= python
COMPOSE = docker compose -f docker/docker-compose.yml

.PHONY: help up down logs ps init backend nlp frontend worker test lint demo prod-up prod-down clean

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

# ---------- 基础设施 ----------
up: ## 启动 Docker Compose 基础设施
	$(COMPOSE) up -d
down: ## 停止基础设施
	$(COMPOSE) down
logs: ## 查看基础设施日志
	$(COMPOSE) logs -f
ps: ## 查看容器状态
	$(COMPOSE) ps
init: ## 初始化（启动基础设施 + 建库 + 建 ES 索引 + 管理员账号）
	$(COMPOSE) up -d
	$(PY) scripts/init_db.py
	$(PY) scripts/init_es_index.py
	$(PY) scripts/seed_admin.py

# ---------- 服务 ----------
backend: ## 启动后端开发服务器
	cd backend && uvicorn app.main:app --reload --port 8000
nlp: ## 启动 NLP 服务
	cd nlp && uvicorn app.main:app --reload --port 8100
frontend: ## 启动前端开发服务器
	cd frontend && npm run dev
worker: ## 启动 ARQ worker
	cd backend && python -m app.worker

# ---------- 测试 / 检查 ----------
test: ## 运行全部测试
	cd backend && pytest
	cd nlp && pytest
	cd frontend && npm test
lint: ## 代码检查
	cd backend && ruff check .
	cd nlp && ruff check .
	cd frontend && npx tsc --noEmit
demo: ## 一键演示：上传样例→导入→推理→训练→发布（需先 make init 并启动四个服务）
	$(PY) scripts/demo.py

# ---------- 生产部署 ----------
prod-up: ## 构建并启动生产栈（需先 export JWT_SECRET_KEY / DB_PASSWORD / MINIO_ROOT_PASSWORD）
	docker compose -f docker/docker-compose.prod.yml up -d --build
prod-down: ## 停止生产栈
	docker compose -f docker/docker-compose.prod.yml down
clean: ## 清理 Python/Node 缓存
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name node_modules -prune -exec rm -rf {} +