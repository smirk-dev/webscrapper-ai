"""CLI to ingest OSINT events from Google Sheets.

Usage:
    python scripts/ingest_from_sheet.py --lane UK-India
    python scripts/ingest_from_sheet.py --lane UK-Egypt
    python scripts/ingest_from_sheet.py --all
    python scripts/ingest_from_sheet.py --lane UK-India --dry-run
    python scripts/ingest_from_sheet.py --all --run-pipeline
    python scripts/ingest_from_sheet.py --all --local
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("advuman.sheet_ingest")

LANE_NAMES = ["UK-India", "UK-Egypt"]


async def ingest_lane(lane_name: str, dry_run: bool) -> dict | None:
    from src.config import settings
    from src.collectors.sheet_ingestor import SheetIngestor

    try:
        url = settings.sheet_tab_url(lane_name)
    except KeyError:
        log.error(
            "No sheet GID configured for lane '%s'. Check OSINT_SHEET_GIDS in .env",
            lane_name,
        )
        return None

    log.info("Ingesting lane: %s  url=%s", lane_name, url)

    ingestor = SheetIngestor(lane_name=lane_name, dry_run=dry_run)
    try:
        stats = await ingestor.ingest(url)
        log.info(
            "Lane %s — fetched=%d  parse_errors=%d  duplicates=%d  inserted=%d",
            lane_name,
            stats["fetched"],
            stats["skipped_parse_error"],
            stats["skipped_duplicate"],
            stats["inserted"],
        )
        return stats
    except Exception as exc:
        log.error("Ingest failed for lane %s: %s", lane_name, exc)
        return None


async def main(args: argparse.Namespace) -> None:
    if args.local:
        db_path = Path(args.sqlite_path).resolve()
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        log.info("Using local SQLite DB: %s", db_path)

    # Lazy import after env var is set so settings + engine pick up the right URL
    from src.db.models import Base
    from src.db.session import engine

    if args.local:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    lanes = LANE_NAMES if args.all else [args.lane]

    total_inserted = 0
    for lane in lanes:
        stats = await ingest_lane(lane, dry_run=args.dry_run)
        if stats:
            total_inserted += stats["inserted"]

    if args.run_pipeline and not args.dry_run and total_inserted > 0:
        for lane in lanes:
            log.info("Running pipeline for %s...", lane)
            pipeline_args = [sys.executable, "scripts/run_pipeline.py", "--lane", lane]
            if args.local:
                pipeline_args.extend(["--local", "--sqlite-path", args.sqlite_path])
            result = subprocess.run(
                pipeline_args, cwd=Path(__file__).resolve().parent.parent
            )
            if result.returncode != 0:
                log.error("Pipeline failed for lane %s", lane)

    log.info("Done. Total inserted: %d", total_inserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest OSINT events from Google Sheets"
    )
    parser.add_argument(
        "--lane",
        default="UK-India",
        choices=LANE_NAMES,
        help="Trade lane to ingest (default: UK-India)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Ingest all configured lanes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and deduplicate without writing to DB",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run the quant pipeline after ingestion",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local SQLite DB for offline development",
    )
    parser.add_argument(
        "--sqlite-path",
        default="advuman_local.db",
        help="SQLite file path used with --local (default: advuman_local.db)",
    )
    args = parser.parse_args()

    # Set env var BEFORE asyncio.run so the first import of src.config uses it
    if args.local:
        db_path = Path(args.sqlite_path).resolve()
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    asyncio.run(main(args))
