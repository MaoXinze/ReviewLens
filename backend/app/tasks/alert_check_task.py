"""ARQ 定时告警检查任务。

作为 worker 的独立函数运行（见 app/worker.py）。主体逻辑在
alert_service.run_alert_check，任务仅做薄封装以适配 ARQ 的 (ctx, ...) 签名与上下文。
异常向上抛出由 ARQ 标记失败，不静默吞错。
"""
from app.core.db import AsyncSessionLocal
from app.services import alert_service


async def run_alert_check(ctx, *_args, **_kwargs) -> dict:
    """遍历 active 告警规则，去重后触发。ctx 为 ARQ worker 上下文（未使用）。"""
    async with AsyncSessionLocal() as db:
        return await alert_service.run_alert_check(db)
