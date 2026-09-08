# M4 - NLP 分析管线

> 项目：ReviewLens | 优先级：P2-P3 | 状态：未开始  
> 前置文档：[架构设计](../02-架构设计说明书.md) | [需求分析](../01-需求分析说明书.md)

## 项目背景（30秒）

ReviewLens 是电商品牌评论体验分析平台。技术栈：FastAPI + React 18 + PostgreSQL 16 + Elasticsearch 8 + Redis + MinIO。NLP 服务在 `nlp/` 目录，是独立的 Python 服务（端口 8100），被 `backend/` 的 FastAPI 通过 HTTP 调用。基础设施通过 `docker/docker-compose.yml` 启动。Python 用本地环境。

## 模块定位

本模块从评论文本中提取属性级情感信号：每条评论识别出"电池续航=负面""充电速度=正面"这样的属性×情感矩阵。是整个平台的核心技术壁垒。

## 依赖关系

- **上游依赖**：M2（数据导入）— 评论数据已入库
- **上游依赖**：M1（认证）— API 鉴权
- **下游被依赖**：
  - M5（审核）— 低置信度预测进入审核队列
  - M6（训练）— 审核后的样本用于训练新模型
  - M7（看板）— 预测结果聚合为洞察
- **前置条件**：M2 导入的评论数据可用；scikit-learn + jieba 已安装

## 数据库表

```sql
-- review_predictions 表（NLP 预测结果）
CREATE TABLE review_predictions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version VARCHAR(100) NOT NULL,
    review_id       VARCHAR(200) NOT NULL,
    model_version   VARCHAR(50) NOT NULL,
    overall_sentiment VARCHAR(20) NOT NULL,   -- positive/neutral/negative
    confidence      FLOAT NOT NULL,            -- 0.0-1.0
    aspects         JSONB NOT NULL,            -- [{"aspect":"电池续航","sentiment":"negative","confidence":0.82}]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (dataset_version, review_id, model_version)
);

CREATE INDEX idx_predictions_dataset ON review_predictions(dataset_version);
CREATE INDEX idx_predictions_review ON review_predictions(dataset_version, review_id);
CREATE INDEX idx_predictions_model ON review_predictions(model_version);
CREATE INDEX idx_predictions_low_conf ON review_predictions(confidence) WHERE confidence < 0.7;

-- analysis_runs 表（训练/分析运行记录）
CREATE TABLE analysis_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version     VARCHAR(100) NOT NULL,
    model_version       VARCHAR(50) UNIQUE NOT NULL,
    algorithm           VARCHAR(30) NOT NULL,    -- tfidf_lr / bert_base
    random_seed         INTEGER NOT NULL DEFAULT 42,
    train_samples       INTEGER NOT NULL DEFAULT 0,
    test_samples        INTEGER NOT NULL DEFAULT 0,
    macro_f1            FLOAT,
    accuracy            FLOAT,
    classification_report JSONB,                -- 完整 sklearn classification_report
    confusion_matrix    JSONB,                   -- [[tn,fp],[fn,tp]]
    status              VARCHAR(20) NOT NULL DEFAULT 'queued', -- queued/running/succeeded/failed
    model_file_sha256   VARCHAR(64),
    model_file_path     VARCHAR(500),            -- MinIO 路径
    publish_status      VARCHAR(20) NOT NULL DEFAULT 'evaluation_only', -- evaluation_only/published/archived
    error_message       TEXT,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    created_by          UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runs_status ON analysis_runs(status);
CREATE INDEX idx_runs_publish ON analysis_runs(publish_status);
```

## API 端点

### 后端 API（对前端）

| 方法 | 路径 | 说明 | 鉴权 | 角色 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/predictions/batch` | 触发批量推理 | 登录 | analyst+ |
| GET | `/api/v1/predictions` | 查询预测结果 | 登录 | - |
| GET | `/api/v1/predictions/low-confidence` | 低置信度列表（供 M5 审核） | 登录 | - |
| POST | `/api/v1/analysis-runs` | 创建训练运行 | 登录 | analyst+ |
| GET | `/api/v1/analysis-runs` | 查询训练运行列表 | 登录 | - |
| GET | `/api/v1/analysis-runs/{id}` | 训练运行详情 | 登录 | - |
| POST | `/api/v1/analysis-runs/{id}/publish` | 发布模型 | 登录 | analyst+ |
| GET | `/api/v1/models/current` | 当前生产模型 | 登录 | - |

### NLP 服务 API（内部，不对前端）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/inference/batch` | 批量推理（接收评论列表，返回预测） |
| POST | `/api/v1/training-runs` | 训练新模型（接收训练数据引用） |
| GET | `/api/v1/training-runs/{id}` | 查询训练状态 |
| GET | `/api/v1/models/{version}` | 模型信息 |
| GET | `/health` | 健康检查 |

## 技术设计

### 基线模型（P2，必须完成）

```python
# nlp/app/services/sentiment_classifier.py

class TfidfLrSentimentClassifier:
    """TF-IDF + Logistic Regression 情感分类基线"""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=50000,
            analyzer='char_wb',  # 字符级+词级混合
        )
        self.classifier = LogisticRegression(
            C=1.0, max_iter=1000,
            class_weight='balanced',
            random_state=42
        )
        self.label_encoder = {'positive': 2, 'neutral': 1, 'negative': 0}

    def train(self, texts: list[str], labels: list[str]):
        X = self.vectorizer.fit_transform(texts)
        y = [self.label_encoder[l] for l in labels]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        self.classifier.fit(X_train, y_train)
        return self.evaluate(X_test, y_test)

    def predict(self, texts: list[str]) -> list[dict]:
        X = self.vectorizer.transform(texts)
        probas = self.classifier.predict_proba(X)
        predictions = []
        for proba in probas:
            idx = proba.argmax()
            confidence = float(proba[idx])
            sentiment = list(self.label_encoder.keys())[list(self.label_encoder.values()).index(idx)]
            predictions.append({'sentiment': sentiment, 'confidence': confidence})
        return predictions

    def save(self, path: str):
        joblib.dump({'vectorizer': self.vectorizer, 'classifier': self.classifier}, path)

    def load(self, path: str):
        data = joblib.load(path)
        self.vectorizer = data['vectorizer']
        self.classifier = data['classifier']
```

### 属性抽取（基线，规则+词表）

```python
# nlp/app/services/aspect_extractor.py

class RuleBasedAspectExtractor:
    """基于受控词表的属性抽取"""

    def __init__(self, taxonomy_path: str):
        self.taxonomy = self._load_taxonomy(taxonomy_path)
        # taxonomy 结构: {"电池续航": {"keywords": ["battery","续航","电池","电量"], ...}, ...}

    def extract(self, text: str) -> list[dict]:
        aspects = []
        for aspect_name, config in self.taxonomy.items():
            for keyword in config['keywords']:
                if keyword.lower() in text.lower():
                    aspects.append({
                        'aspect': aspect_name,
                        'keyword': keyword,
                        'sentiment': self._infer_sentiment(text, keyword),
                        'confidence': 0.7  # 规则匹配默认置信度
                    })
                    break  # 每个属性只匹配一次
        return aspects

    def _infer_sentiment(self, text: str, keyword: str) -> str:
        """基于关键词上下文的简单情感推断"""
        # 找到关键词位置，检查前后 10 个词的情感词
        # 正面词：good, great, fast, 不错, 好, 快
        # 负面词：bad, poor, slow, 差, 慢, 坏
        # 如果找不到情感词，返回 neutral
        ...
```

### 属性词表

```json
// nlp/app/data/aspect_taxonomy.json
{
  "电池续航": { "keywords": ["battery life", "battery", "续航", "电池", "电量", "充电一次"] },
  "充电速度": { "keywords": ["charging speed", "charge fast", "快充", "充电速度", "慢充"] },
  "屏幕显示": { "keywords": ["screen", "display", "屏幕", "显示", "分辨率", "色彩"] },
  "性能速度": { "keywords": ["performance", "fast", "slow", "性能", "卡顿", "流畅"] },
  "音质": { "keywords": ["sound", "audio", "音质", "噪音", "声音", "扬声器"] },
  "外观设计": { "keywords": ["design", "appearance", "外观", "设计", "颜值", "做工"] },
  "包装": { "keywords": ["packaging", "package", "包装", "破损", "盒子"] },
  "售後服务": { "keywords": ["customer service", "warranty", "售后", "客服", "退换", "维修"] },
  "价格价值": { "keywords": ["price", "value", "价格", "性价比", "贵", "划算"] },
  "物流配送": { "keywords": ["delivery", "shipping", "物流", "快递", "发货", "配送"] },
  "可靠性": { "keywords": ["quality", "durable", "broke", "质量", "故障", "坏", "耐用"] },
  "安全性": { "keywords": ["safe", "hot", "安全", "发热", "起火", "烫"] }
}
```

### 批量推理流程

```text
1. backend 收到 POST /predictions/batch，指定 dataset_version
2. backend 提交 ARQ 任务
3. ARQ Worker:
   a. 从 PostgreSQL 读取该 dataset_version 的所有评论（分批 1000 条）
   b. 调用 NLP 服务 POST /api/v1/inference/batch
   c. NLP 服务返回每条评论的预测结果
   d. Worker 将结果写入 review_predictions 表
   e. 同步更新 ES 索引中的 aspects 和 overall_sentiment 字段
   f. 置信度 < 0.7 的样本标记为待审核
4. 完成后更新任务状态
```

### 训练流程

```text
1. backend 收到 POST /analysis-runs，指定 dataset_version
2. backend 查询该版本下 status=approved/verified 的审核任务
3. 校验：approved+verified 样本 >= 200 条，否则拒绝
4. 创建 analysis_run 记录（status=queued）
5. 调用 NLP 服务 POST /api/v1/training-runs
6. NLP 服务：
   a. 从 backend API 获取训练数据（审核后的评论+标签）
   b. 构建 TF-IDF + LR 管线
   c. train_test_split(test_size=0.2, random_state=42, stratify=labels)
   d. 训练 + 评测
   e. 保存模型到 MinIO
   f. 返回指标
7. backend 更新 analysis_run：macro_f1, accuracy, status=succeeded
8. 如果 Macro-F1 >= 0.70 且 test_samples >= 1000：允许发布
```

## 实现清单

### NLP 服务（nlp/ 目录）

- [ ] 创建 `nlp/app/main.py` — FastAPI app 入口
- [ ] 创建 `nlp/app/core/config.py` — NLP 服务配置
- [ ] 创建 `nlp/app/data/aspect_taxonomy.json` — 属性词表
- [ ] 创建 `nlp/app/services/preprocessing.py` — 文本清洗+分词
- [ ] 创建 `nlp/app/services/aspect_extractor.py` — 属性抽取
- [ ] 创建 `nlp/app/services/sentiment_classifier.py` — 情感分类（TF-IDF + LR）
- [ ] 创建 `nlp/app/services/training.py` — 训练管线
- [ ] 创建 `nlp/app/services/evaluation.py` — 评测管线
- [ ] 创建 `nlp/app/api/routes.py` — NLP 服务路由
- [ ] 创建 `nlp/requirements.txt` — NLP 依赖
- [ ] 创建 `nlp/tests/test_aspect_extraction.py` — 属性抽取测试
- [ ] 创建 `nlp/tests/test_sentiment_classification.py` — 情感分类测试

### 后端（backend/ 目录）

- [ ] 创建 `backend/app/models/prediction.py` — ReviewPrediction + AnalysisRun ORM 模型
- [ ] 创建 `backend/app/schemas/prediction.py` — 请求/响应模型
- [ ] 创建 `backend/app/services/nlp_client.py` — NLP 服务 HTTP 客户端
- [ ] 创建 `backend/app/tasks/inference_task.py` — ARQ 批量推理任务
- [ ] 创建 `backend/app/api/v1/predictions.py` — 预测路由
- [ ] 创建 `backend/app/api/v1/analysis_runs.py` — 训练运行路由
- [ ] 创建 `backend/alembic/versions/004_create_predictions.py` — 迁移脚本
- [ ] 创建 `backend/tests/test_predictions.py` — 预测测试

## 验收标准

1. 属性抽取覆盖率 >= 60%（至少 60% 的评论命中至少一个属性）
2. 情感分类 Macro-F1 >= 0.70（独立测试集 >= 1000 条）
3. 批量推理 10 万条评论在 30 分钟内完成
4. 每条预测可追溯到 model_version 和 dataset_version
5. 置信度 < 0.7 的样本自动标记待审核
6. 训练可复现：相同数据 + seed=42 → 相同指标
7. 指标低于门槛时 publish_status = evaluation_only

## 文件清单

```
nlp/app/
├── main.py
├── core/
│   └── config.py
├── data/
│   └── aspect_taxonomy.json
├── services/
│   ├── preprocessing.py
│   ├── aspect_extractor.py
│   ├── sentiment_classifier.py
│   ├── training.py
│   └── evaluation.py
├── api/
│   └── routes.py
nlp/requirements.txt
nlp/tests/
├── test_aspect_extraction.py
└── test_sentiment_classification.py

backend/app/
├── models/
│   └── prediction.py
├── schemas/
│   └── prediction.py
├── services/
│   └── nlp_client.py
├── tasks/
│   └── inference_task.py
├── api/v1/
│   ├── predictions.py
│   └── analysis_runs.py
├── alembic/versions/
│   └── 004_create_predictions.py
backend/tests/
└── test_predictions.py
```
