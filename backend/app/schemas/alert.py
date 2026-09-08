"""M9 告警与导出的请求/响应模型。

- AlertRuleOut / AlertRenderOut：告警规则及其最近一次渲染的告警。
- AlertOut：告警记录（含规则名/类型/触发值/指标值）。
- ExportRecordOut：导出记录。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RuleType = Literal["threshold", "trend"]
RuleStatus = Literal["active", "paused"]
AlertStatus = Literal["active", "acknowledged", "resolved"]


# ---------- 告警规则 ----------


class AlertRuleCreateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    rule_type: RuleType
    aspect: str = Field(..., max_length=50)
    product_id: str | None = Field(default=None, max_length=100)
    threshold_value: float = Field(..., gt=0)
    time_window_days: int = Field(default=30, ge=1, le=365)
    dedup_days: int = Field(default=7, ge=1, le=365)
    webhook_url: str | None = Field(default=None, max_length=500)


class AlertRuleUpdateRequest(BaseModel):
    """更新规则：主要支持暂停/恢复（active ↔ paused）。"""

    status: RuleStatus


class AlertRuleOut(BaseModel):
    id: str
    name: str
    rule_type: str
    aspect: str
    product_id: str | None = None
    threshold_value: float
    time_window_days: int
    dedup_days: int
    webhook_url: str | None = None
    status: str
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertRuleListResponse(BaseModel):
    items: list[AlertRuleOut]
    total: int
    page: int
    page_size: int


# ---------- 告警 ----------


class AlertOut(BaseModel):
    id: str
    rule_id: str
    rule_name: str = ""
    rule_type: str = ""
    aspect: str
    product_id: str | None = None
    metric_value: float
    trigger_value: float
    status: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    model_config = {"from_attributes": True}


class AlertUpdateRequest(BaseModel):
    """确认/解决告警：active→acknowledged→resolved。"""

    status: AlertStatus


class AlertListResponse(BaseModel):
    items: list[AlertOut]
    total: int
    page: int
    page_size: int


# ---------- 导出 ----------


class ExportCreateRequest(BaseModel):
    dataset_version: str
    product_id: str | None = None
    sentiment: str | None = None  # predicted sentiment 过滤
    rating_min: int | None = Field(default=None, ge=1, le=5)
    rating_max: int | None = Field(default=None, ge=1, le=5)


class ExportRecordOut(BaseModel):
    id: str
    exported_by: str
    dataset_version: str
    filters: dict
    file_path: str
    row_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportListResponse(BaseModel):
    items: list[ExportRecordOut]
    total: int
    page: int
    page_size: int
