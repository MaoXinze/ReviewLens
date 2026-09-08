# ReviewLens 分发指南

> 作用：给你（用户）用。每个模块的分发指令模板，复制粘贴到对应窗口即可。

## 协作铁则（违反则立即返工）

### 1. 项目无 git 管理，直接操作文件

- **本项目没有 git，不要 git init，不要 git add/commit/push，不要建分支**

- 所有文件直接读写，改完就是改完了

- 如果有人误执行了 git init，立即删除 `.git/` 目录

### 2. 完成后更新进度文档

- 修改 `docs/03-版本迭代路线图.md` 中对应模块的状态为 ✅ 已完成

- 追加 `.workbuddy/memory/2026-09-02.md` 的项目进度部分

### 3. 其他窗口必读

新窗口开始前先读 `.workbuddy/memory/2026-09-02.md` 了解历史，再读 `docs/03-版本迭代路线图.md` 了解当前进度。

## 使用方法

1. 选择你要分发的模块
2. 复制对应区块的"分发指令"（代码块内的全部内容）
3. 粘贴到新窗口（新 TRAE 会话）
4. 对应窗口按指令执行

## 项目文档索引（所有窗口通用）

```
docs/01-需求分析说明书.md      — 需求全貌
docs/02-架构设计说明书.md      — 技术选型+架构+数据模型+API
docs/03-版本迭代路线图.md      — 全局进度看板
docs/modules/M{N}-{名称}.md   — 各模块自包含设计文档
```

***

## M10 - 部署与工程化（P1 首选）

> 备注：M10 项目骨架已由其他窗口搭建。若再次分发，应按验收标准检查当前状态后补遗，无需从零搭建。

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中对应模块状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M10 部署与工程化模块：

1. docs/02-架构设计说明书.md（§3 技术选型、§5 目录结构、§10 部署拓扑、§11 环境与依赖）
2. docs/modules/M10-部署与工程化.md（本模块设计文档，含实现清单）

项目背景：ReviewLens 是电商评论分析平台。技术栈 FastAPI + React 18 + PostgreSQL 16 + Elasticsearch 8 + Redis + MinIO。

你的任务：
- 创建 docker/docker-compose.yml（4 个基础设施容器，分组名 reviewlens）
- 创建 backend/ 和 nlp/ 和 frontend/ 的项目骨架
- 创建 requirements.txt 和 package.json
- 创建 .env.example 文件
- 创建 Makefile
- 创建 .gitignore
- 初始化 git 仓库（如尚未初始化）

注意：Elasticsearch 8.15.0 镜像需要拉取，先问用户是否同意。
Python/Node 使用本地环境（uv/conda），不走 Docker。

完成后请更新 docs/03-版本迭代路线图.md 中 M10 的状态为 ✅ 已完成。
```

***

## M1 - 认证与权限（P1）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M1 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M1 认证与权限模块：

1. docs/02-架构设计说明书.md（§3.1 后端框架、§6.1 数据模型、§7.2 API、§8 安全设计）
2. docs/modules/M1-认证与权限.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。后端 FastAPI + PostgreSQL 16 + SQLAlchemy 2.0 + Alembic。
项目骨架已创建（backend/app/ 目录结构已存在）。

你的任务：按 M1 文档中的实现清单逐项完成：
- User 和 AuditLog ORM 模型
- JWT 签发/验证 + bcrypt 密码哈希
- Pydantic Settings 配置
- 认证路由（register/login/me）
- 权限控制依赖注入（require_role）
- Alembic 迁移脚本
- pytest 测试

完成后请更新 docs/03-版本迭代路线图.md 中 M1 的状态为 ✅ 已完成。
```

***

## M2 - 数据导入引擎（P2）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M2 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M2 数据导入引擎模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型 datasets/reviews 表、§6.2 ES 索引、§7.2 API）
2. docs/modules/M2-数据导入引擎.md（本模块设计文档，含校验规则、导入流程、实现清单）

项目背景：ReviewLens 是电商评论分析平台。M1 认证模块已完成。
后端 FastAPI + PostgreSQL 16 + Elasticsearch 8 + Redis + ARQ + MinIO。

你的任务：按 M2 文档中的实现清单逐项完成：
- Dataset 和 Review ORM 模型（含分区）
- CSV/JSONL 解析器
- 9 条校验规则
- ARQ 异步导入任务（PG + ES 双写）
- 数据集路由
- 质量报告生成
- Amazon Reviews 下载脚本

完成后请更新 docs/03-版本迭代路线图.md 中 M2 的状态为 ✅ 已完成。
```

***

## M3 - 评论搜索引擎（P2）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M3 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M3 评论搜索引擎模块：

1. docs/02-架构设计说明书.md（§3.4 Elasticsearch、§6.2 ES 索引映射、§7.2 API）
2. docs/modules/M3-评论搜索引擎.md（本模块设计文档，含查询构建、聚合逻辑、实现清单）

项目背景：ReviewLens 是电商评论分析平台。M2 数据导入已完成，评论已写入 ES 索引。
后端 FastAPI + Elasticsearch 8 + IK 分词器。

你的任务：按 M3 文档中的实现清单逐项完成：
- Elasticsearch AsyncClient + IK 分词器初始化
- 全文搜索（multi_match + IK 分词 + 高亮）
- 分面聚合（属性差评率、评分分布、时间趋势）
- 搜索路由
- ES 索引初始化脚本

完成后请更新 docs/03-版本迭代路线图.md 中 M3 的状态为 ✅ 已完成。
```

***

## M4 - NLP 分析管线（P2-P3）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M4 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M4 NLP 分析管线模块：

1. docs/02-架构设计说明书.md（§3.7 NLP 技术栈、§6.1 review_predictions/analysis_runs 表、§7.3 NLP 服务 API）
2. docs/modules/M4-NLP分析管线.md（本模块设计文档，含基线算法代码、属性词表、训练/推理流程、实现清单）
3. docs/01-需求分析说明书.md（§4.3 NLP 分析管线、§4.3 算法设计细节）

项目背景：ReviewLens 是电商评论分析平台。M2 数据导入已完成，评论数据可用。
NLP 服务是独立的 Python 服务（nlp/ 目录，端口 8100），被 backend 通过 HTTP 调用。
技术：scikit-learn + jieba + transformers（P3 可选）。

你的任务：按 M4 文档中的实现清单逐项完成：
NLP 服务（nlp/）:
- 文本预处理 + jieba 分词
- 规则+词表属性抽取器
- TF-IDF + LR 情感分类器
- 训练管线（train_test_split + seed=42）
- 评测管线（Macro-F1 + 混淆矩阵 + 分类报告）
- 批量推理 API
后端（backend/）:
- ReviewPrediction + AnalysisRun ORM
- NLP 服务 HTTP 客户端
- ARQ 批量推理任务
- 预测和训练运行路由

注意：基线模型不依赖 GPU。BERT 为 P3 进阶项，不阻塞 P2 交付。

完成后请更新 docs/03-版本迭代路线图.md 中 M4 的状态为 ✅ 已完成。
```

***

## M5 - 人工审核工作流（P3）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M5 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M5 人工审核工作流模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型、§7.2 API）
2. docs/modules/M5-人工审核工作流.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。前序模块（M4 NLP 预测结果）已完成。
后端 FastAPI + PostgreSQL + React 18 + Ant Design 5。

你的任务：按 M5 文档中的实现清单逐项完成。
完成后请更新 docs/03-版本迭代路线图.md 中 M5 的状态为 ✅ 已完成。
```

***

## M6 - 模型训练与评测（P3）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M6 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M6 模型训练与评测模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型、§7.2 API）
2. docs/modules/M6-模型训练与评测.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。前序模块（M4 NLP 服务、M5 审核样本）已完成。
后端 FastAPI + PostgreSQL + React 18。

你的任务：按 M6 文档中的实现清单逐项完成。
完成后请更新 docs/03-版本迭代路线图.md 中 M6 的状态为 ✅ 已完成。
```

***

## M7 - 体验洞察看板（P3）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M7 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M7 体验洞察看板模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型、§7.2 API）
2. docs/modules/M7-体验洞察看板.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。前序模块（M3 ES 搜索聚合、M4 NLP 预测）已完成。
后端 FastAPI + PostgreSQL + React 18 + Ant Design 5 + @ant-design/charts。

你的任务：按 M7 文档中的实现清单逐项完成。
完成后请更新 docs/03-版本迭代路线图.md 中 M7 的状态为 ✅ 已完成。
```

***

## M8 - 问题卡管理（P4）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M8 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M8 问题卡管理模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型、§7.2 API）
2. docs/modules/M8-问题卡管理.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。前序模块（M7 看板洞察）已完成。
后端 FastAPI + PostgreSQL + React 18。

你的任务：按 M8 文档中的实现清单逐项完成。
完成后请更新 docs/03-版本迭代路线图.md 中 M8 的状态为 ✅ 已完成。
```

***

## M9 - 告警与导出（P4）

```
【协作铁则 —— 开始前必读，违反则返工】
1. 项目无 git 管理：不要 git init/add/commit/push，不要建分支。直接读写文件即可。误建 .git/ 立即删除。
2. 完成后更新 docs/03-版本迭代路线图.md 中 M9 状态为 ✅，追加 .workbuddy/memory/2026-09-02.md 进度。
3. 开始前先读 .workbuddy/memory/2026-09-02.md（历史）和 docs/03-版本迭代路线图.md（当前进度）。

请阅读以下项目文档，然后实现 M9 告警与导出模块：

1. docs/02-架构设计说明书.md（§6.1 数据模型、§7.2 API）
2. docs/modules/M9-告警与导出.md（本模块设计文档，含实现清单和验收标准）

项目背景：ReviewLens 是电商评论分析平台。前序模块（M7 看板聚合）已完成。
后端 FastAPI + PostgreSQL + React 18。

你的任务：按 M9 文档中的实现清单逐项完成。
完成后请更新 docs/03-版本迭代路线图.md 中 M9 的状态为 ✅ 已完成。
```

***

## 注意事项

1. **分发前确认前置模块已完成**：检查路线图中对应模块状态为 ✅
2. **每个窗口只负责一个模块**：不要在一个窗口塞多个模块
3. **完成后更新路线图**：这是唯一的进度同步机制
4. **ES 镜像需用户确认拉取**：任何涉及 Docker 镜像拉取的操作都需先问用户

