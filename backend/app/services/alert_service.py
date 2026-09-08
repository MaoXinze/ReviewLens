"""告警服务（M9）。

职责：
- create_rule / list_rules / update_rule_status：告警规则增查改（active ↔ paused）。
- evaluate_rule：单规则判定（threshold 阈值 / trend 环比增长）。
- run_alert_check：遍历 active 规则，去重后触发符合条件的告警（验收标准 1、2）。
- 去重：同一规则在 dedup_days 内已有告警则不重复触发（验收标准 3）。
- update_alert_status：告警状态机 active → acknowledged → resolved（验收标准 4）。

差评率复用 M8 issue_service._aspect_negative_rate（数据口径与 M7 看板一致），
计算目标数据集取最近一次成功导入的 completed 数据集。
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import (
    ALERT_STATUS_ACKNOWLEDGED,
    ALERT_STATUS_ACTIVE,
    ALERT_STATUS_RESOLVED,
    ALERT_TRANSITIONS,
    RULE_STATUS_ACTIVE,
    RULE_STATUS_PAUSED,
    Alert,
    AlertRule,
)
from app.models.user import User
from app.services.issue_service import _aspect_negative_rate, get_latest_dataset


class AlertEvaluationError(Exception):
    """ES 差评率计算失败（转 503）。"""


def _now() -> datetime:
    return datetime.now(UTC)


async def create_rule(db: AsyncSession, *, req, creator: User) -> AlertRule:
    """创建告警规则。阈值与去重天数做范围校验。"""
    if req.rule_type not in ("threshold", "trend"):
        raise ValueError("rule_type 仅支持 threshold / trend")
    if req.dedup_days > req.time_window_days:
        raise ValueError("去重天数不能大于监控窗口天数")
    rule = AlertRule(
        id=str(uuid4()),
        name=req.name,
        rule_type=req.rule_type,
        aspect=req.aspect,
        product_id=req.product_id,
        threshold_value=req.threshold_value,
        time_window_days=req.time_window_days,
        dedup_days=req.dedup_days,
        webhook_url=req.webhook_url,
        status=RULE_STATUS_ACTIVE,
        created_by=creator.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(
    db: AsyncSession,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AlertRule], int]:
    stmt = select(AlertRule)
    count_stmt = select(func.count()).select_from(AlertRule)
    if status:
        stmt = stmt.where(AlertRule.status == status)
        count_stmt = count_stmt.where(AlertRule.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(AlertRule.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_rule(db: AsyncSession, rule_id: str) -> AlertRule | None:
    return await db.get(AlertRule, rule_id)


async def update_rule_status(
    db: AsyncSession, rule: AlertRule, *, status: str
) -> AlertRule:
    if status == rule.status:
        raise ValueError(f"状态已是 {status}")
    if status not in (RULE_STATUS_ACTIVE, RULE_STATUS_PAUSED):
        raise ValueError("状态仅支持 active / paused")
    rule.status = status
    await db.commit()
    await db.refresh(rule)
    return rule


def _recent_alert_cutoff(rule: AlertRule) -> datetime:
    return _now() - timedelta(days=rule.dedup_days)


async def has_recent_alert(db: AsyncSession, rule: AlertRule) -> bool:
    """去重：同一规则在 dedup_days 内是否有告警（无论状态）。"""
    stmt = select(func.count()).select_from(Alert).where(
        Alert.rule_id == rule.id,
        Alert.triggered_at >= _recent_alert_cutoff(rule),
    )
    count = (await db.execute(stmt)).scalar_one()
    return int(count) > 0


async def evaluate_rule(
    db: AsyncSession, rule: AlertRule
) -> Alert | None:
    """判定单规则是否触发，触发则创建 Alert（未 commit）。

    返回新 Alert；未触发或无可用数据返回 None。
    """
    latest = await get_latest_dataset(db)
    if latest is None:
        return None
    ds = latest.dataset_version
    now = _now()
    start = now - timedelta(days=rule.time_window_days)

    try:
        current_rate = await _aspect_negative_rate(
            db,
            dataset_version=ds,
            aspect=rule.aspect,
            product_id=rule.product_id,
            start_date=start,
        )
    except Exception as exc:  # 差评率异常统一抛出，交由任务/路由处理
        raise AlertEvaluationError(f"告警差评率查询失败: {exc}") from exc

    metric = current_rate
    if rule.rule_type == "threshold":
        if current_rate <= rule.threshold_value:
            return None
    else:  # trend
        prev_rate = await _aspect_negative_rate(
            db,
            dataset_version=ds,
            aspect=rule.aspect,
            product_id=rule.product_id,
            start_date=now - timedelta(days=2 * rule.time_window_days),
            end_date=start,
        )
        growth = (
            (current_rate - prev_rate) / prev_rate if prev_rate > 0 else 0.0
        )
        metric = round(growth, 4)
        if growth <= rule.threshold_value:
            return None

    return Alert(
        id=str(uuid4()),
        rule_id=rule.id,
        aspect=rule.aspect,
        product_id=rule.product_id,
        metric_value=metric,
        trigger_value=rule.threshold_value,
        status=ALERT_STATUS_ACTIVE,
    )


async def _notify_webhook(rule: AlertRule, alert: Alert) -> None:
    """触发告警时向规则的 webhook_url 发送 JSON 通知（失败静默，不阻断主流程）。"""
    if not rule.webhook_url:
        return
    try:
        import httpx

        payload = {
            "event": "reviewlens.alert",
            "alert_id": alert.id,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "rule_type": rule.rule_type,
            "aspect": rule.aspect,
            "product_id": rule.product_id,
            "metric_value": alert.metric_value,
            "trigger_value": alert.trigger_value,
            "status": alert.status,
            "triggered_at": alert.triggered_at.isoformat(),
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(rule.webhook_url, json=payload)
    except Exception:  # 通知失败不应导致告警检查失败
        pass


async def run_alert_check(db: AsyncSession) -> dict:
    """遍历所有 active 规则，去重后触发。返回统计。"""
    result = await db.execute(
        select(AlertRule).where(AlertRule.status == RULE_STATUS_ACTIVE)
    )
    rules = list(result.scalars().all())
    created = 0
    for rule in rules:
        if await has_recent_alert(db, rule):
            continue
        alert = await evaluate_rule(db, rule)
        if alert is not None:
            db.add(alert)
            created += 1
            await _notify_webhook(rule, alert)
    await db.commit()
    return {"checked": len(rules), "created": created}


async def list_alerts(
    db: AsyncSession,
    *,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Alert], int]:
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)
    if status:
        if status not in (
            ALERT_STATUS_ACTIVE,
            ALERT_STATUS_ACKNOWLEDGED,
            ALERT_STATUS_RESOLVED,
        ):
            raise ValueError("status 仅支持 active / acknowledged / resolved")
        stmt = stmt.where(Alert.status == status)
        count_stmt = count_stmt.where(Alert.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(Alert.triggered_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def update_alert_status(
    db: AsyncSession, alert: Alert, *, status: str, operator: User
) -> Alert:
    """推进告警状态机（active→acknowledged→resolved，resolved 终态）。"""
    if status == alert.status:
        raise ValueError(f"状态已是 {status}")
    allowed = ALERT_TRANSITIONS.get(alert.status, set())
    if status not in allowed:
        raise ValueError(f"不允许从 {alert.status} 流转到 {status}")
    alert.status = status
    if status == ALERT_STATUS_RESOLVED:
        alert.resolved_at = _now()
        alert.resolved_by = operator.id
    await db.commit()
    await db.refresh(alert)
    return alert
