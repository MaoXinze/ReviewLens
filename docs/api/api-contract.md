# ReviewLens 后端端点契约

> 用途：一站式列出后端全部 HTTP 端点及其请求/响应契约，供前端实现、联调与测试参考。
> 响应信封统一为 `{"code": 0, "data": ...}`；出错时为 `{"detail": "..."}`（FastAPI 默认），部分路径业务错误也返回此结构。
> 鉴权：除 `/api/auth/register|login|refresh` 外均需 `Authorization: Bearer <token>`。
> 角色权限（由高到低）：`admin` > `analyst` > `operator` > `user(默认) ` 。角色标注省略 admin（admin 拥有所有权限）。

***

## 1. 认证（M1）— 前缀 `/api/auth`

| 方法   | 路径         | 鉴权    | 说明                                |
| ---- | ---------- | ----- | --------------------------------- |
| POST | `register` | 公开    | 注册新用户（角色固定 `operator`）            |
| POST | `login`    | 公开    | 登录，返回 access + refresh token      |
| POST | `refresh`  | 公开    | 用 refresh\_token 换新 access\_token |
| GET  | `me`       | user+ | 当前登录用户信息                          |
| PUT  | `me`       | user+ | 更新自己的 `full_name`                 |

**register** — 请求：

```json
{ "email": "a@b.com", "password": "Passw0rd!", "full_name": "Tony" }
```

响应 `data`：`{ id, email, full_name, role }`；邮箱重复 → 409。

**login** — 请求：`{ "email": "...", "password": "..." }`
响应 `data`：`{ access_token, refresh_token, expires_in }`；密码错 → 401，禁用 → 403。

**refresh** — 请求：`{ "refresh_token": "..." }`
响应 `data`：同 login（`refresh_token` 原样返回）。

**me (GET)** — 响应 `data`：`{ id, email, full_name, role, is_active, created_at }`。

**me (PUT)** — 请求：`{ "full_name": "..." }`（可空）；响应同 GET me。

***

## 2. 数据导入（M2）— 前缀 `/api/v1/datasets`

| 方法   | 路径                         | 鉴权        | 说明                        |
| ---- | -------------------------- | --------- | ------------------------- |
| POST | `imports`                  | operator+ | 上传 CSV/JSONL 触发异步导入 → 202 |
| GET  | \`\`（空）                    | user+     | 数据集列表（分页）                 |
| GET  | `{version}`                | user+     | 数据集详情 + 质量报告              |
| GET  | `{version}/quality-report` | user+     | 质量报告详情                    |
| GET  | `{version}/reviews`        | user+     | 数据集内评论列表                  |

**imports** — `multipart/form-data`：字段 `file`（必填）、`field_mapping`（可选 JSON 字符串）。
响应 `data`：`{ job_id, status, message, dataset_version, reused }`。

**数据集列表** — Query：`page`(默认1) `page_size`(默认20,≤100)。
响应 `data`：`{ items: Dataset[], total, page, page_size }`。

**Dataset 对象**：

```
dataset_version  string
source_filename  string
file_sha256      string
total_rows       int
valid_rows       int
rejected_rows    int
quality_report   object|null   { rejection_reasons, reasons_detail }
status           string        queued|processing|completed|failed
error_message    string|null
created_at       datetime
```

**quality-report** — 响应 `data`：`{ rejection_reasons: { reason: count }, reasons_detail: { reason: [样例...] } }`。

**{version}/reviews** — Query：分页同上。响应 `data.items` 为 `Review[]`：

```
id, review_id, product_id, product_group_id?, review_title?,
review_text, rating?, reviewed_at, reviewer_id?,
helpful_votes, verified_purchase, language
```

***

## 3. 评论搜索（M3）— 前缀 `/api/v1/reviews`

| 方法   | 路径          | 鉴权    | 说明                |
| ---- | ----------- | ----- | ----------------- |
| POST | `search`    | user+ | 全文检索（IK 分词 + 高亮）  |
| POST | `aggregate` | user+ | 分面聚合（属性/评分/时间/情感） |

**search** — 请求：

```json
{
  "query": "battery",
  "filters": {
    "dataset_version": null, "product_id": null, "product_group_id": null,
    "rating_min": null, "rating_max": null, "date_from": null, "date_to": null,
    "language": null, "overall_sentiment": null, "aspect": null
  },
  "page": 1, "page_size": 20, "sort_by": "relevance"
}
```

`sort_by` ∈ `relevance|date|helpful`。ES 不可用 → 503。
响应 `data`：`{ items: SearchHit[], total, page, page_size, took_ms }`。

**SearchHit**：

```
review_id, product_id, product_group_id?, review_title?,
review_text, rating?, reviewed_at?, language?, helpful_votes,
verified_purchase, overall_sentiment?, highlight: string[]   // <em> 包高亮词
```

**aggregate** — 请求：

```json
{ "dataset_version": null, "group_by": "aspect", "date_histogram": "week",
  "filters": { "product_id": null, "product_group_id": null, "rating_min": null,
               "rating_max": null, "date_from": null, "date_to": null, "language": null } }
```

`group_by` ∈ `aspect|rating|date|sentiment`；`date_histogram` ∈ `day|week|month`。
响应 `data`：`{ buckets: [{ key, doc_count, negative_count, negative_rate, positive_count?, neutral_count?, avg_confidence? }], total_docs, took_ms }`。

***

## 4. NLP 预测（M4）— 前缀 `/api/v1/predictions`

| 方法   | 路径               | 鉴权        | 说明               |
| ---- | ---------------- | --------- | ---------------- |
| POST | `batch`          | operator+ | 触发批量推理 → 202     |
| GET  | \`\`             | user+     | 预测结果（分页）         |
| GET  | `low-confidence` | user+     | 置信度过低列表（供 M5 审核） |

**batch** — 请求：`{ "dataset_version": "...", "model_version": null }`
响应 `data`：`{ status, message, dataset_version, model_version, job_id }`。

**列表 / low-confidence** — Query：`dataset_version` `model_version`(仅列表) `page` `page_size`。
响应 `data`：`{ items, total, page, page_size }`。
`PredictionOut`：`{ review_id, dataset_version, model_version, overall_sentiment, confidence, aspects: [...], created_at }`。
`LowConfidenceOut`：`{ review_id, overall_sentiment, confidence, aspects, model_version, dataset_version }`。

***

## 5. 人工审核（M5）— 前缀 `/api/v1/review-tasks`

| 方法    | 路径                        | 鉴权        | 说明                  |
| ----- | ------------------------- | --------- | ------------------- |
| POST  | `generate`                | analyst+  | 从预测结果生成任务 → 201     |
| GET   | \`\`                      | user+     | 任务列表（按状态/采样组/数据集筛选） |
| GET   | `next`                    | operator+ | 下一条待审核（连续审核）        |
| GET   | `summary`                 | user+     | 审核进度统计              |
| GET   | `{task_id}`               | user+     | 任务详情（含原文引用）         |
| PATCH | `{task_id}`               | operator+ | 提交审核结果              |
| POST  | `{task_id}/second-review` | analyst+  | 二次复核                |

**generate** — 请求：`{ "dataset_version": "...", "model_version": null, "count": 50 }`（count∈\[1,5000]）。
响应 `data`：`{ created, dataset_version, skipped }`。

**next** — Query：`dataset_version`(可选)。响应 `data` 为 `ReviewTaskOut|null`（无任务时 null）。

**ReviewTaskOut**（详情/next 携带原文）：

```
id, dataset_version, review_id, sampling_group, sampling_reason?,
system_sentiment?, system_confidence?, system_aspects?: [{aspect,sentiment,confidence}],
model_version?, reviewer_sentiment?, reviewer_aspects?, review_reason?, review_note?,
status, reviewer_id?, reviewed_at?, second_reviewer_id?, second_reviewed_at?, created_at,
review_title?, review_text?, rating?      // 原文，仅 Out 有
```

`status` ∈ `pending|approved|rejected|awaiting_second_review|verified|cancelled`。

**PATCH {task\_id}** — 请求：

```json
{ "status": "approved", "reviewer_sentiment": "positive",
  "reviewer_aspects": [], "review_reason": "confirm_prediction", "review_note": null }
```

`status` ∈ `approved|rejected`；`review_reason` ∈ `confirm_prediction|correct_sentiment|correct_aspects|correct_both|invalid_text|insufficient_info`。响应 ReviewTaskOut。

**second-review** — 请求：`{ "status": "approved|rejected", "review_note": null }`。响应 ReviewTaskOut。

**summary** — Query：`dataset_version`(可选)。响应 `data`：

```
{ dataset_version?, total, done, pending, approved, verified, rejected,
  completion_rate, agreement_rate }   // 均为 0~1 的小数比例
```

**列表** — Query：`status` `sampling_group` `dataset_version` `page` `page_size`。
响应 `data`：`{ items: ReviewTaskListItem[], total, page, page_size }`（ListItem 无原文字段）。

***

## 6. 训练与模型（M4/M6）— 前缀 `/api/v1`

| 方法   | 路径                            | 鉴权       | 说明                       |
| ---- | ----------------------------- | -------- | ------------------------ |
| POST | `analysis-runs`               | analyst+ | 弱标签训练运行                  |
| POST | `analysis-runs/reviewed`      | analyst+ | 用 approved/verified 样本训练 |
| GET  | `analysis-runs`               | user+    | 训练运行列表                   |
| GET  | `analysis-runs/{id}`          | user+    | 训练运行详情                   |
| POST | `analysis-runs/{id}/publish`  | analyst+ | 发布模型（校验门槛）               |
| POST | `analysis-runs/{id}/rollback` | analyst+ | 回滚到上一发布版本                |
| GET  | `models/current`              | user+    | 当前生产模型                   |
| GET  | `models/history`              | user+    | 模型版本历史                   |
| GET  | `models/{run_id}/criteria`    | user+    | 发布门槛检查                   |

**创建训练运行** — 请求：`{ "dataset_version": "...", "algorithm": "tfidf_lr", "min_samples": null }`
`algorithm` ∈ `tfidf_lr|bert_base`。NLP 服务不可用 → 502。响应 `AnalysisRunOut`。

**AnalysisRunOut**：

```
id, dataset_version, model_version, algorithm, random_seed,
train_samples, test_samples, macro_f1?, accuracy?,
classification_report?, confusion_matrix?, status, publish_status,
error_message?, started_at?, finished_at?, created_at
```

`status` ∈ `queued|running|succeeded|failed`；`publish_status` ∈ `evaluation_only|published|archived`。

**publish** — 响应 `data`：`{ status: published|unchanged, message, model_version }`。

**rollback** — 响应 `data`：`{ message, previous_model_version|null, has_previous }`。

**models/current** — 响应当前模型；无模型时 `{ publish_status: "no_model" }`。

**models/history** — 响应 `data`：`{ items: ModelOut[], total }`。

**models/{run\_id}/criteria** — 响应 `data`：

```
{ macro_f1?, macro_f1_ok, test_samples, test_samples_ok,
  coverage?, coverage_ok, can_publish, reasons: string[],
  metrics?: { classification_report?, confusion_matrix?, macro_f1?, accuracy? } }
```

***

## 7. 体验洞察（M7）— 前缀 `/api/v1/insights`

| 方法  | 路径               | 鉴权    | 说明                     |
| --- | ---------------- | ----- | ---------------------- |
| GET | `overview`       | user+ | 总览（评论量/情感分布/差评属性/审核进度） |
| GET | `aspect-ranking` | user+ | 属性差评率排行 + 环比           |
| GET | `trends`         | user+ | 差评率趋势时间序列              |
| GET | `sku-comparison` | user+ | 多 SKU 属性对比             |
| GET | `evidence`       | user+ | 聚合数字 → 证据评论下钻          |

通用 Query：`dataset_version`(必填) `product_id`(可选)。

- **aspect-ranking**：另支持 `period`(可选)。

- **trends**：支持 `granularity=month|week`(默认 month) `aspect`。

- **sku-comparison**：`skus`(必填，逗号分隔) `aspect`(可选)。

- **evidence**：`page` `page_size` `aspect` `sentiment` `period`。

ES 不可用 → 503；参数错误 → 400。响应 `data` 结构见 `app/services/insight_service.py`。

***

## 8. 用户管理（M1）— 前缀 `/api/v1/users`

| 方法    | 路径          | 鉴权    | 说明     |
| ----- | ----------- | ----- | ------ |
| GET   | \`\`        | admin | 用户列表   |
| PATCH | `{id}/role` | admin | 修改用户角色 |

Query（列表）：`page` `page_size`。响应 `data`：`{ items: UserOut[], total, page, page_size }`。
PATCH 请求：`{ "role": "analyst" }`，`role` ∈ `operator|analyst|admin`；响应 UserOut。

***

## 9. 问题卡（M8）— 前缀 `/api/v1/issues`

| 方法    | 路径                | 鉴权        | 说明           |
| ----- | ----------------- | --------- | ------------ |
| POST  | \`\`              | operator+ | 创建问题卡 → 201  |
| GET   | \`\`              | user+     | 问题卡列表        |
| GET   | `{id}`            | user+     | 问题卡详情（含审计轨迹） |
| PATCH | `{id}`            | operator+ | 推进状态         |
| POST  | `{id}/retrospect` | operator+ | 效果回测         |

**POST / 列表** — Query（列表）：`status` `aspect` `assignee` `dataset_version` `page` `page_size`。
创建请求：

```json
{ "dataset_version": "...", "title": "...", "aspect": "battery",
  "severity": "high", "description": null, "source_review_ids": ["R1"],
  "assignee": null }
```

`severity` ∈ `low|medium|high|critical`。

**Issue**：

```
id, dataset_version, title, aspect, severity, status, description?,
source_review_ids: string[], assignee?, resolution_note?,
validation_note?, created_by, created_at, updated_at, closed_at?
```

`status` ∈ `open|in_progress|pending_validation|closed`。

**PATCH {id}** — 请求：`{ "status": "in_progress", "resolution_note": null, "validation_note": null }`。
状态机：`open→in_progress→pending_validation→closed`（非法流转 → 400）。

**{id}** 详情 — 响应 `data`：`{ issue, history: [{ field_name, old_value, new_value, changed_by, changed_at, reason }] }`。

**retrospect** — 响应 `data`：`{ issue_id, dataset_version, aspect, pre_rate, post_rate, change, improved }`。

***

## 10. 告警与导出（M9）— 前缀 `/api/v1/alert-rules` `/api/v1/alerts` `/api/v1/exports`

### 告警规则 `/api/v1/alert-rules`

| 方法    | 路径          | 鉴权       | 说明                   |
| ----- | ----------- | -------- | -------------------- |
| POST  | \`\`        | analyst+ | 创建规则 → 201           |
| GET   | \`\`        | user+    | 规则列表                 |
| PATCH | `{rule_id}` | analyst+ | 暂停/恢复（active↔paused） |

创建请求：

```json
{ "name": "...", "rule_type": "threshold", "aspect": "battery",
  "product_id": null, "threshold_value": 0.3,
  "time_window_days": 30, "dedup_days": 7 }
```

`rule_type` ∈ `threshold|trend`；`time_window_days/dedup_days` ∈ \[1,365]。
响应 `AlertRuleOut`：`{ name, rule_type, aspect, product_id?, threshold_value, time_window_days, dedup_days, status, created_by, created_at, ... }`。
PATCH 请求：`{ "status": "active|paused" }`。

### 告警 `/api/v1/alerts`

| 方法    | 路径           | 鉴权        | 说明                                  |
| ----- | ------------ | --------- | ----------------------------------- |
| GET   | \`\`         | user+     | 告警列表（按状态筛选）                         |
| PATCH | `{alert_id}` | operator+ | 确认/解决（active→acknowledged→resolved） |

列表 Query：`status` `page` `page_size`。响应 `AlertOut`：

```
{ id, rule_id, rule_name, rule_type, aspect, product_id?,
  metric_value, trigger_value, status, triggered_at, resolved_at?, resolved_by? }
```

PATCH 请求：`{ "status": "active|acknowledged|resolved" }`。

### 导出 `/api/v1/exports`

| 方法   | 路径                     | 鉴权       | 说明           |
| ---- | ---------------------- | -------- | ------------ |
| POST | \`\`                   | analyst+ | 导出 CSV → 201 |
| GET  | \`\`                   | user+    | 导出记录列表       |
| GET  | `{export_id}/download` | analyst+ | 下载 CSV 文件    |

创建请求：

```json
{ "dataset_version": "...", "product_id": null, "sentiment": null,
  "rating_min": null, "rating_max": null }
```

响应 `ExportRecordOut`：`{ id, exported_by, dataset_version, filters, file_path, row_count, created_at }`。
下载返回 `text/csv` 流；文件不存在 → 404，读取失败 → 503。

***

## 附录 A：通用约定

- **分页**：统一 `page`(≥1，默认1) + `page_size`(默认20，≤100)，响应含 `total/page/page_size`。

- **错误**：鉴权失败 `401`、无权限 `403`、资源不存在 `404`、参数错误 `400`、外部依赖不可用（NLP/ES/MinIO/存储）`503`（部分 NLP `502`）。

- **时间**：字段为 ISO-8601 字符串（`datetime`）。

- **状态码**：列表/详情/更新 `200`；创建资源统一用 `201`（部分异步提交用 `202`，已在表中标注）。

