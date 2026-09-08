"""ARQ Worker 启动入口：python -m app.worker。

worker 独立于 FastAPI 进程运行，消费 Redis 队列中的导入/推理/定时告警检查任务。
"""
from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import Worker

from app.core.config import settings
from app.tasks.alert_check_task import run_alert_check
from app.tasks.import_task import run_import
from app.tasks.inference_task import run_inference

# 定时任务：每天 08:00（服务器时区）运行一次告警规则检查
cron_jobs = [cron(run_alert_check, hour=8, minute=0)]


def main() -> None:
    worker = Worker(
        functions=[run_import, run_inference, run_alert_check],
        cron_jobs=cron_jobs,
        redis_settings=RedisSettings.from_dsn(settings.redis_url),
    )
    worker.run()


if __name__ == "__main__":
    main()
