"""Schedule recurring source-sync + scraping + pipeline runs.

Usage examples:
    python scripts/schedule_sync_scrape.py --lane UK-India --minutes 60
    python scripts/schedule_sync_scrape.py --lane UK-India --daily-at 09:00
"""

import argparse
import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

ROOT_DIR = Path(__file__).resolve().parent.parent


async def _create_run_log(lane: str, trigger: str) -> int | None:
    from sqlalchemy import select

    from src.db.models import PipelineRun, RunStatus, TradeLane
    from src.db.session import async_session

    async with async_session() as session:
        lane_result = await session.execute(select(TradeLane).where(TradeLane.name == lane))
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


async def _finalize_run_log(run_id: int | None, success: bool, details: str, error_summary: str | None) -> None:
    if run_id is None:
        return

    from sqlalchemy import select

    from src.db.models import PipelineRun, RunStatus
    from src.db.session import async_session

    async with async_session() as session:
        result = await session.execute(select(PipelineRun).where(PipelineRun.id == run_id))
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


def _job(lane: str, no_llm: bool, local: bool, sqlite_path: str) -> None:
    print(f"\n[{datetime.now().isoformat(timespec='seconds')}] Starting scheduled run for lane={lane}")
    run_id = None
    try:
        run_id = asyncio.run(_create_run_log(lane=lane, trigger="scheduler"))
    except Exception as exc:
        print(f"Warning: could not create run log row: {exc}")

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
    print("Collectors output:\n" + "\n".join(out_collectors.splitlines()[-80:]))
    if not ok_collectors:
        print("Scheduled run failed at collector stage.")
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
            print(f"Warning: could not finalize run log row: {exc}")
        return

    pipeline_args = ["scripts/run_pipeline.py", "--lane", lane]
    if local:
        pipeline_args.extend(["--local", "--sqlite-path", sqlite_path])

    ok_pipeline, out_pipeline = _run_command(pipeline_args)
    print("Pipeline output:\n" + "\n".join(out_pipeline.splitlines()[-80:]))
    if not ok_pipeline:
        print("Scheduled run failed at pipeline stage.")
        try:
            asyncio.run(
                _finalize_run_log(
                    run_id,
                    success=False,
                    details=f"{out_collectors}\n\n{out_pipeline}",
                    error_summary="Pipeline stage failed",
                )
            )
        except Exception as exc:
            print(f"Warning: could not finalize run log row: {exc}")
        return

    print(f"[{datetime.now().isoformat(timespec='seconds')}] Scheduled run completed successfully")
    try:
        asyncio.run(
            _finalize_run_log(
                run_id,
                success=True,
                details=f"{out_collectors}\n\n{out_pipeline}",
                error_summary=None,
            )
        )
    except Exception as exc:
        print(f"Warning: could not finalize run log row: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Schedule periodic source sync + scrape + pipeline runs")
    parser.add_argument("--lane", default="UK-India", help="Trade lane name")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM classification")
    parser.add_argument("--minutes", type=int, default=60, help="Run interval in minutes")
    parser.add_argument(
        "--daily-at",
        default="",
        help="Optional HH:MM (24h) to run once daily instead of interval",
    )
    parser.add_argument("--local", action="store_true", help="Use local SQLite DB")
    parser.add_argument("--sqlite-path", default="advuman_local.db", help="SQLite DB file path")
    args = parser.parse_args()

    scheduler = BlockingScheduler()

    if args.daily_at:
        hour, minute = args.daily_at.split(":")
        scheduler.add_job(
            _job,
            "cron",
            hour=int(hour),
            minute=int(minute),
            kwargs={
                "lane": args.lane,
                "no_llm": args.no_llm,
                "local": args.local,
                "sqlite_path": args.sqlite_path,
            },
            id="advuman_daily_run",
            replace_existing=True,
        )
        print(f"Scheduled daily run at {args.daily_at} for lane={args.lane}")
    else:
        scheduler.add_job(
            _job,
            "interval",
            minutes=max(args.minutes, 1),
            kwargs={
                "lane": args.lane,
                "no_llm": args.no_llm,
                "local": args.local,
                "sqlite_path": args.sqlite_path,
            },
            id="advuman_interval_run",
            replace_existing=True,
            next_run_time=datetime.now(),
        )
        print(f"Scheduled interval run every {max(args.minutes, 1)} minute(s) for lane={args.lane}")

    print("Press Ctrl+C to stop scheduler.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    main()
