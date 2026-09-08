"""M9 告警与导出 ORM 模型。

- alert_rules：告警规则。当属性差评率超阈值（threshold）或环比增长异常（trend）时，
  在最近时间窗口内监控并触发告警；支持按 SKU（product_id）、窗口天数、去重天数配置。
- alerts：告警记录。状态机 active → acknowledged → resolved，
  resolved 需记录解决人与时间。
- export_records：导出记录。每次 CSV 导出的筛选条件（JSONB）与 MinIO 文件路径，
  供离线分析溯源。

时间字段沿用 Python 侧默认（M2 教训，规避 asyncpg 批量 RETURNING 兼容问题）。
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 告警规则类型
RULE_TYPE_THRESHOLD = "threshold"
RULE_TYPE_TREND = "trend"
VALID_RULE_TYPES = {RULE_TYPE_THRESHOLD, RULE_TYPE_TREND}

# 规则状态
RULE_STATUS_ACTIVE = "active"
RULE_STATUS_PAUSED = "paused"
VALID_RULE_STATUSES = {RULE_STATUS_ACTIVE, RULE_STATUS_PAUSED}

# 告警状态机
ALERT_STATUS_ACTIVE = "active"
ALERT_STATUS_ACKNOWLEDGED = "acknowledged"
ALERT_STATUS_RESOLVED = "resolved"
VALID_ALERT_STATUSES = {
    ALERT_STATUS_ACTIVE,
    ALERT_STATUS_ACKNOWLEDGED,
    ALERT_STATUS_RESOLVED,
}
# 状态流转白名单：{当前状态: {目标状态}}
ALERT_TRANSITIONS: dict[str, set[str]] = {
    ALERT_STATUS_ACTIVE: {ALERT_STATUS_ACKNOWLEDGED, ALERT_STATUS_RESOLVED},
    ALERT_STATUS_ACKNOWLEDGED: {ALERT_STATUS_RESOLVED},
    ALERT_STATUS_RESOLVED: set(),  # 终态，不可流转
}


class AlertRule(Base):
    """告警规则。"""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    aspect: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    time_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    dedup_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RULE_STATUS_ACTIVE, index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class Alert(Base):
    """告警记录。"""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    rule_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("alert_rules.id"), nullable=False, index=True
    )
    aspect: Mapped[str] = mapped_column(String(50), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_value: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ALERT_STATUS_ACTIVE, index=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True
    )


class ExportRecord(Base):
    """导出记录。"""

    __tablename__ = "export_records"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    exported_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=False
    )
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
