# ReviewLens

面向电商品牌运营的商品评论体验分析平台。

- 拆解商品评论，量化属性（物流/品质/外观/服务/性价比等）差评率
- 定位问题商品与问题属性，驱动改进闭环

## 技术栈

FastAPI + React 18 + PostgreSQL 16 + Elasticsearch 8 + Redis + MinIO + ARQ + scikit-learn

## 快速开始

要求：Docker、Python 3.12（uv/conda 本地环境）、Node 22。

### 方式一：一键脚本（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev_start.ps1
```

脚本依次启动 Docker 基础设施 → backend(:8000) → nlp(:8100) → frontend(:5173) → ARQ worker，日志写入 `.workbuddy/logs/`。

### 方式二：手动分步启动

```bash
# 1. 启动基础设施（首次会构建含 IK 的 ES 镜像，需可访问 Docker Hub / GitHub）
docker compose -f docker/docker-compose.yml up -d

# 2. 等待健康检查通过后初始化（建库 + 建 ES 索引 + 创建管理员账号）
make init

# 3. 本地启动四个服务（分别开四个终端）
make backend      # :8000
make nlp          # :8100
make frontend     # :5173
make worker       # ARQ worker（必须启动，否则导入/推理/定时告警不执行）
```

### 首次登录

`make init` 会自动创建管理员账号（默认 `admin@reviewlens.dev`，随机密码打印在终端）。也可通过环境变量自定义：

```bash
ADMIN_EMAIL=admin@mycompany.com ADMIN_PASSWORD=yourpass python scripts/seed_admin.py
```

> 注意：注册接口默认开放（角色 operator）。管理员登录后可进入「用户管理」调整角色。

### 一键演示（推荐）

服务全部启动后，跑一次端到端演示（上传样例数据 → 导入 → 批量推理 → 训练 → 发布模型）：

```bash
make demo
```

完成后打开前端「洞察看板」选择对应数据集，即可查看情感分布、属性差评率与趋势下钻。样例数据为 Amazon Appliances 评论 30000 条（`data/Appliances.sample30000.jsonl`）。

## 生产部署

全部服务已容器化（backend / nlp / frontend / worker / 基础设施），一条命令起整套：

```bash
export JWT_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
export DB_PASSWORD=<数据库密码>
export MINIO_ROOT_PASSWORD=<MinIO密码>
# 可选：ADMIN_EMAIL / ADMIN_PASSWORD / FRONTEND_PORT / BACKEND_PORT
docker compose -f docker/docker-compose.prod.yml up -d --build
```

- bootstrap 服务自动完成数据库迁移、ES 索引初始化与管理员 seeding（随机密码见 `docker compose logs bootstrap`）
- 前端经 nginx 同源反代 `/api`，浏览器只需访问 `http://<host>/`
- NLP 镜像为推理精简版（基线模型；需要 DistilBERT 训练/级联复核时基于完整 `nlp/requirements.txt` 自行构建）
- 数据导入对 JSONL（含 .gz）为流式处理，内存占用与文件大小解耦；CSV 为整体解析

## 文档

- `docs/01-需求分析说明书.md` / `docs/02-架构设计说明书.md` / `docs/03-版本迭代路线图.md`
- `docs/modules/M{N}-*.md` 各模块设计文档
- `docs/DISPATCH.md` 模块分发指南

## 进度

见 `docs/03-版本迭代路线图.md`。当前 P0-P5 全部完成：P0 需求设计、P1 基础设施（M10 部署/M1 认证）、P2 数据闭环（导入/搜索/NLP）、P3 分析闭环（审核/训练/看板）、P4 运营闭环（问题卡/告警导出）、P5 工程交付（CI/CD + 前端测试 + E2E 端到端通过 + 契约文档）均已完成。