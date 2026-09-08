"""M8 问题卡管理的请求/响应模型。

- IssueOut：问题卡完整信息（含创建者/负责人/审计摘要）。
- CreateIssueRequest：从看板洞察创建问题卡（operator+）。
- UpdateIssueRequest：推进状态机 + 填写处置/验证结论（operator+）。
- RetrospectResponse：关闭后效果回测（创建前后差评率对比）。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
IssueStatus = Literal[
    "open", "in_progress", "pending_validation", "closed"
]


class IssueOut(BaseModel):
    id: str
    dataset_version: str
    title: str
    aspect: str
    severity: str
    status: str
    description: str | None = None
    source_review_ids: list[str]
    assignee: str | None = None
    resolution_note: str | None = None
    validation_note: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None

    model_config = {"from_attributes": True}


class IssueListItem(IssueOut):
    pass


class IssueListResponse(BaseModel):
    items: list[IssueListItem]
    total: int
    page: int
    page_size: int


class IssueCreateRequest(BaseModel):
    dataset_version: str
    title: str = Field(..., max_length=200)
    aspect: str = Field(..., max_length=50)
    severity: Severity
    description: str | None = Field(default=None, max_length=4000)
    source_review_ids: list[str] = Field(default_factory=list)
    assignee: str | None = None


class IssueUpdateRequest(BaseModel):
    """推进问题卡状态。

    依据目标状态需携带的字段：
      → in_progress：resolution_note（处置说明）
      → open：退回，无需额外字段
      → pending_validation：处置完成
      → in_progress（从 pending_validation）：验证失败退回
      → closed：必须填写 validation_note（验证结论，终态）
    """

    status: IssueStatus
    resolution_note: str | None = Field(default=None, max_length=4000)
    validation_note: str | None = Field(default=None, max_length=4000)


class RetrospectResponse(BaseModel):
    issue_id: str
    dataset_version: str
    aspect: str
    pre_rate: float  # 创建时的差评率（最近数据集，创建时间之前）
    post_rate: float  # 关闭时的差评率（最新数据集，创建时间之后）
    change: float  # post_rate - pre_rate
    improved: bool  # post_rate < pre_rate
