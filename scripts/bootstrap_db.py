"""Run DB migration + seed in one command.

Modes:
- Default: Cloud/Postgres mode (Alembic upgrade + seed)
- Local: SQLite mode (`--local`) for offline development

Also handles Windows + Python 3.14 SQLAlchemy C-extension runtime issues.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path


if sys.platform == "win32" and sys.version_info >= (3, 14):
    os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT_RUNTIME", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Advuman database")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local SQLite DB (offline dev mode), skipping Alembic and creating schema from models",
    )
    parser.add_argument(
        "--sqlite-path",
        default="advuman_local.db",
        help="SQLite file path used with --local (default: advuman_local.db)",
    )
    return parser.parse_args()


def configure_local_database(sqlite_path: str) -> Path:
    db_path = Path(sqlite_path).resolve()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    return db_path


def run_migrations() -> None:
    from alembic.config import main as alembic_main

    result = alembic_main(argv=["upgrade", "head"])
    if result not in (None, 0):
        raise SystemExit(result)


def run_seed() -> None:
    from src.db.seed import main as seed_main

    asyncio.run(seed_main())


def run_local_schema_create() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.config import settings
    from src.db.models import Base

    async def _create() -> None:
        engine = create_async_engine(settings.database_url, echo=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


if __name__ == "__main__":
    args = parse_args()
    try:
        if args.local:
            db_path = configure_local_database(args.sqlite_path)
            run_local_schema_create()
            print(f"Local schema ready: {db_path}")
        else:
            run_migrations()
        run_seed()
        print("Database bootstrap complete.")
    except Exception as exc:
        message = str(exc)
        print(f"Database bootstrap failed: {exc}")
        if "WinError 121" in message or "semaphore timeout" in message.lower():
            print(
                "Hint: network timeout to database host. Run 'python scripts/check_db_connection.py' "
                "and verify DATABASE_URL, VPN/firewall, allowlist, and SSL settings."
            )
        raise