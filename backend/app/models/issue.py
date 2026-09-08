"""问题卡管理 ORM 模型（M8）。

- issues：从看板洞察转化为的可追踪问题卡，记录所属数据集、属性、
  严重度、状态机流转、处置/验证结论，并按状态流转写入审计轨迹。
- issue_history：每次字段变更（status/assignee/severity/resolution_note/
  validation_note）的审计记录，记录「谁、何时、改了什么、为什么」。

状态机：
  open → in_progress（填写处置说明）
  in_progress → open（退回）
  in_progress → pending_validation（处置完成，待验证）
  pending_validation → in_progress（验证失败退回）
  pending_validation → closed（必须填验证结论，终态，不可流转）
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 问题卡状态机取值
ISSUE_STATUS_OPEN = "open"
ISSUE_STATUS_IN_PROGRESS = "in_progress"
ISSUE_STATUS_PENDING_VALIDATION = "pending_validation"
ISSUE_STATUS_CLOSED = "closed"
VALID_ISSUE_STATUSES = {
    ISSUE_STATUS_OPEN,
    ISSUE_STATUS_IN_PROGRESS,
    ISSUE_STATUS_PENDING_VALIDATION,
    ISSUE_STATUS_CLOSED,
}

# 严重度
VALID_SEVERITIES = {"low", "medium", "high", "critical"}

# 状态迁移白名单：{当前状态: {目标状态}}
ISSUE_TRANSITIONS: dict[str, set[str]] = {
    ISSUE_STATUS_OPEN: {ISSUE_STATUS_IN_PROGRESS},
    ISSUE_STATUS_IN_PROGRESS: {ISSUE_STATUS_OPEN, ISSUE_STATUS_PENDING_VALIDATION},
    ISSUE_STATUS_PENDING_VALIDATION: {ISSUE_STATUS_IN_PROGRESS, ISSUE_STATUS_CLOSED},
    ISSUE_STATUS_CLOSED: set(),  # 终态，不可流转
}


class Issue(Base):
    """问题卡。"""

    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    aspect: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ISSUE_STATUS_OPEN, index=True
    )
    description: Mapped[str | None] = mapped_column(nullable=True)
    source_review_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    assignee: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True, index=True
    )
    resolution_note: Mapped[str | None] = mapped_column(nullable=True)
    validation_note: Mapped[str | None] = mapped_column(nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IssueHistory(Base):
    """问题卡变更审计轨迹。"""

    __tablename__ = "issue_history"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    issue_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("issues.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(nullable=True)
    new_value: Mapped[str | None] = mapped_column(nullable=True)
    changed_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    reason: Mapped[str | None] = mapped_column(nullable=True)
