"""Schedule recurring source-sync + scraping + pipeline runs.

Usage examples:
    python scripts/schedule_sync_scrape.py --lane UK-India --minutes 60
    python scripts/schedule_sync_scrape.py --lane UK-India --daily-at 09:00
"""

import argparse
import asyncio
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

ROOT_DIR = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("advuman.scheduler")


async def _create_run_log(lane: str, trigger: str) -> int | None:
    from sqlalchemy import select

    from src.db.models import PipelineRun, RunStatus, TradeLane
    from src.db.session import async_session

    async with async_session() as session:
        lane_result = await session.execute(
            select(TradeLane).where(TradeLane.name == lane)
        )
        lane_row = lane_result.scalar_one_or_none()

        run = PipelineRun(
            trade_lane_id=lane_row.id if lane_row else None,
            trigger=trigger,
            stage="collectors+pipeline",
            status=RunStatus.STARTED,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


async def _finalize_run_log(
    run_id: int | None, success: bool, details: str, error_summary: str | None
) -> None:
    if run_id is None:
        return

    from sqlalchemy import select

    from src.db.models import PipelineRun, RunStatus
    from src.db.session import async_session

    async with async_session() as session:
        result = await session.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return

        run.status = RunStatus.SUCCESS if success else RunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.details = details[:8000] if details else None
        run.error_summary = (error_summary or "")[:2000] or None
        await session.commit()


def _run_command(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return result.returncode == 0, output.strip()


def _job(
    lane: str, no_llm: bool, local: bool, sqlite_path: str, sheet_ingest: bool
) -> None:
    log.info("Starting scheduled run for lane=%s", lane)
    run_id = None
    try:
        run_id = asyncio.run(_create_run_log(lane=lane, trigger="scheduler"))
    except Exception as exc:
        log.warning("Could not create run log row: %s", exc)

    all_output: list[str] = []

    # ── Stage 1: OSINT collectors ────────────────────────────────────────────
    collectors_args = [
        "scripts/run_collectors.py",
        "--all",
        "--persist",
        "--lane",
        lane,
    ]
    if no_llm:
        collectors_args.append("--no-llm")
    if local:
        collectors_args.extend(["--local", "--sqlite-path", sqlite_path])

    ok_collectors, out_collectors = _run_command(collectors_args)
    log.info(
        "Collectors output (last 80 lines):\n%s",
        "\n".join(out_collectors.splitlines()[-80:]),
    )
    all_output.append(out_collectors)

    if not ok_collectors:
        log.error("Scheduled run failed at collector stage.")
        try:
            asyncio.run(
                _finalize_run_log(
                    run_id,
                    success=False,
                    details=out_collectors,
                    error_summary="Collector stage failed",
                )
            )
        except Exception as exc:
            log.warning("Could not finalize run log row: %s", exc)
        return

    # ── Stage 2: Google Sheets ingest (optional) ─────────────────────────────
    if sheet_ingest:
        ingest_args = ["scripts/ingest_from_sheet.py", "--lane", lane]
        if local:
            ingest_args.extend(["--local", "--sqlite-path", sqlite_path])

        ok_ingest, out_ingest = _run_command(ingest_args)
        log.info("Sheet ingest output:\n%s", out_ingest)
        all_output.append(out_ingest)

        if not ok_ingest:
            # Non-fatal: log warning but continue to pipeline
            log.warning(
                "Sheet ingest stage failed (continuing to pipeline):\n%s", out_ingest
            )

    # ── Stage 3: Quant pipeline ──────────────────────────────────────────────
    pipeline_args = ["scripts/run_pipeline.py", "--lane", lane]
    if local:
        pipeline_args.extend(["--local", "--sqlite-path", sqlite_path])

    ok_pipeline, out_pipeline = _run_command(pipeline_args)
    log.info(
        "Pipeline output (last 80 lines):\n%s",
        "\n".join(out_pipeline.splitlines()[-80:]),
    )
    all_output.append(out_pipeline)

    if not ok_pipeline:
        log.error("Scheduled run failed at pipeline stage.")
        try:
            asyncio.run(
                _finalize_run_log(
                    run_id,
                    success=False,
                    details="\n\n".join(all_output),
                    error_summary="Pipeline stage failed",
                )
            )
        except Exception as exc:
            log.warning("Could not finalize run log row: %s", exc)
        return

    log.info("Scheduled run completed successfully for lane=%s", lane)
    try:
        asyncio.run(
            _finalize_run_log(
                run_id,
                success=True,
                details="\n\n".join(all_output),
                error_summary=None,
            )
        )
    except Exception as exc:
        log.warning("Could not finalize run log row: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schedule periodic source sync + scrape + pipeline runs"
    )
    parser.add_argument("--lane", default="UK-India", help="Trade lane name")
    parser.add_argument(
        "--no-llm", action="store_true", help="Disable LLM classification"
    )
    parser.add_argument(
        "--minutes", type=int, default=60, help="Run interval in minutes"
    )
    parser.add_argument(
        "--daily-at",
        default="",
        help="Optional HH:MM (24h) to run once daily instead of interval",
    )
    parser.add_argument("--local", action="store_true", help="Use local SQLite DB")
    parser.add_argument(
        "--sqlite-path", default="advuman_local.db", help="SQLite DB file path"
    )
    parser.add_argument(
        "--sheet-ingest",
        action="store_true",
        help="Pull analyst events from Google Sheets after collectors and before pipeline",
    )
    args = parser.parse_args()

    job_kwargs = {
        "lane": args.lane,
        "no_llm": args.no_llm,
        "local": args.local,
        "sqlite_path": args.sqlite_path,
        "sheet_ingest": args.sheet_ingest,
    }

    scheduler = BlockingScheduler()

    if args.daily_at:
        hour, minute = args.daily_at.split(":")
        scheduler.add_job(
            _job,
            "cron",
            hour=int(hour),
            minute=int(minute),
            kwargs=job_kwargs,
            id="advuman_daily_run",
            replace_existing=True,
        )
        log.info(
            "Scheduled daily run at %s for lane=%s (sheet_ingest=%s)",
            args.daily_at,
            args.lane,
            args.sheet_ingest,
        )
    else:
        scheduler.add_job(
            _job,
            "interval",
            minutes=max(args.minutes, 1),
            kwargs=job_kwargs,
            id="advuman_interval_run",
            replace_existing=True,
            next_run_time=datetime.now(),
        )
        log.info(
            "Scheduled interval run every %d minute(s) for lane=%s (sheet_ingest=%s)",
            max(args.minutes, 1),
            args.lane,
            args.sheet_ingest,
        )

    log.info("Press Ctrl+C to stop scheduler.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
