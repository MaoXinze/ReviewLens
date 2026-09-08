"""初始化数据库 schema。

运行 Alembic 迁移（upgrade head），确保 users / audit_logs 等表就绪。
需先启动 PostgreSQL（docker compose up -d）并配置 backend/.env 的 DATABASE_URL。
"""
import os
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path，便于以包方式运行 alembic
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    os.chdir(BACKEND_DIR)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    print("[init_db] 开始执行数据库迁移...")
    command.upgrade(cfg, "head")
    print("[init_db] 迁移完成，数据库 schema 已就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())