"""CLI to run the quant pipeline on collected events.

Usage:
    python scripts/run_pipeline.py --lane uk-india
    python scripts/run_pipeline.py --lane uk-india --week 2026-02-17
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def run_pipeline(lane_name: str, week_start: date | None = None) -> None:
    from sqlalchemy import select

    from src.config import settings
    from src.db.models import Event, IndexSnapshot, IndexType, LaneHealth, TradeLane
    from src.db.session import async_session
    from src.pipeline.cusum import CUSUMDetector, CUSUMState
    from src.pipeline.ewma import EWMABaseline
    from src.pipeline.attribution import compute_attribution
    from src.pipeline.rollup import compute_lane_health
    from src.pipeline.scoring import compute_weighted_score
    from src.pipeline.zscore import compute_zscore

    if week_start is None:
        # Default to current week (Monday)
        today = date.today()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=4)  # Friday

    print(f"Running pipeline for {lane_name} | Week: {week_start} to {week_end}")
    print("=" * 60)

    async with async_session() as session:
        # Find the trade lane
        result = await session.execute(
            select(TradeLane).where(TradeLane.name == lane_name)
        )
        lane = result.scalar_one_or_none()
        if not lane:
            print(f"Trade lane '{lane_name}' not found.")
            return

        # Get events for this week
        result = await session.execute(
            select(Event)
            .where(Event.trade_lane_id == lane.id)
            .where(Event.date_observed >= week_start)
            .where(Event.date_observed <= week_end)
            .order_by(Event.date_observed)
        )
        events = result.scalars().all()

        if not events:
            print("No events found for this week. Persisting zero snapshots.")
        else:
            print(f"Found {len(events)} events\n")

        # Compute weighted scores
        rpi_total = 0.0
        lsi_total = 0.0
        cpi_total = 0.0
        rpi_weighted = 0.0
        lsi_weighted = 0.0
        cpi_weighted = 0.0
        attribution_data = []

        for event in events:
            score, src_w, stat_w, conf_w, prec_w = compute_weighted_score(
                delta=event.index_delta,
                source_layer=event.source_layer,
                event_status=event.event_status,
                confidence_level=event.confidence_level,
                historical_precedent=event.historical_precedent,
            )

            if event.index_impact == IndexType.RPI:
                rpi_total += event.index_delta
                rpi_weighted += score
            elif event.index_impact == IndexType.LSI:
                lsi_total += event.index_delta
                lsi_weighted += score
            elif event.index_impact == IndexType.CPI:
                cpi_total += event.index_delta
                cpi_weighted += score

            attribution_data.append({
                "weighted_score": score,
                "source_layer": event.source_layer.value,
                "impact_pathway": event.impact_pathway,
                "jurisdiction": event.jurisdiction.value,
            })

            print(
                f"  {event.date_observed} | {event.index_impact.value:3s} "
                f"| delta={event.index_delta:+d} | weighted={score:+.3f} "
                f"| {event.event_description[:60]}"
            )

        # Lane Health
        combined, health = compute_lane_health(rpi_total, lsi_total, cpi_total)

        print(f"\n{'─'*60}")
        print(f"WEEKLY ROLL-UP:")
        print(f"  RPI Total:  {rpi_total:+.0f}")
        print(f"  LSI Total:  {lsi_total:+.0f}")
        print(f"  CPI Total:  {cpi_total:+.0f}")
        print(f"  Combined:   {combined:+.0f}")
        print(f"  Lane Health: {health.value}")

        # Persist weekly lane health (upsert by lane + week_start)
        existing_health = await session.execute(
            select(LaneHealth)
            .where(LaneHealth.trade_lane_id == lane.id)
            .where(LaneHealth.week_start == week_start)
        )
        health_row = existing_health.scalar_one_or_none()
        if health_row is None:
            health_row = LaneHealth(
                trade_lane_id=lane.id,
                week_start=week_start,
                week_end=week_end,
                rpi_total=rpi_total,
                lsi_total=lsi_total,
                cpi_total=cpi_total,
                combined_total=combined,
                health_status=health,
            )
            session.add(health_row)
        else:
            health_row.week_end = week_end
            health_row.rpi_total = rpi_total
            health_row.lsi_total = lsi_total
            health_row.cpi_total = cpi_total
            health_row.combined_total = combined
            health_row.health_status = health

        weighted_by_index = {
            IndexType.RPI: rpi_weighted,
            IndexType.LSI: lsi_weighted,
            IndexType.CPI: cpi_weighted,
        }
        raw_by_index = {
            IndexType.RPI: rpi_total,
            IndexType.LSI: lsi_total,
            IndexType.CPI: cpi_total,
        }
        lambda_by_index = {
            IndexType.RPI: settings.ewma_lambda_rpi,
            IndexType.LSI: settings.ewma_lambda_lsi,
            IndexType.CPI: settings.ewma_lambda_cpi,
        }

        for idx_type in [IndexType.RPI, IndexType.LSI, IndexType.CPI]:
            previous_result = await session.execute(
                select(IndexSnapshot)
                .where(IndexSnapshot.trade_lane_id == lane.id)
                .where(IndexSnapshot.index_type == idx_type)
                .where(IndexSnapshot.date < week_end)
                .order_by(IndexSnapshot.date.desc())
                .limit(1)
            )
            previous = previous_result.scalar_one_or_none()

            ewma = EWMABaseline(lam=lambda_by_index[idx_type])
            if previous and previous.ewma_mean is not None:
                ewma.mean = previous.ewma_mean
                ewma.variance = (previous.ewma_sigma or 0.0) ** 2

            current_weighted = weighted_by_index[idx_type]
            ewma_mean, ewma_sigma = ewma.update(current_weighted)
            z_score = compute_zscore(current_weighted, ewma_mean, ewma_sigma)

            cusum_upper = None
            cusum_lower = None
            if idx_type == IndexType.RPI:
                detector = CUSUMDetector(k=settings.cusum_k, h=settings.cusum_h)
                if previous and previous.cusum_upper is not None and previous.cusum_lower is not None:
                    detector.state = CUSUMState(upper=previous.cusum_upper, lower=previous.cusum_lower)
                if z_score is not None:
                    state, _ = detector.update(z_score)
                    cusum_upper = state.upper
                    cusum_lower = state.lower

            existing_snapshot_result = await session.execute(
                select(IndexSnapshot)
                .where(IndexSnapshot.trade_lane_id == lane.id)
                .where(IndexSnapshot.date == week_end)
                .where(IndexSnapshot.index_type == idx_type)
            )
            snapshot = existing_snapshot_result.scalar_one_or_none()
            if snapshot is None:
                snapshot = IndexSnapshot(
                    trade_lane_id=lane.id,
                    date=week_end,
                    index_type=idx_type,
                    raw_total=raw_by_index[idx_type],
                    weighted_total=current_weighted,
                    z_score=z_score,
                    ewma_mean=ewma_mean,
                    ewma_sigma=ewma_sigma,
                    cusum_upper=cusum_upper,
                    cusum_lower=cusum_lower,
                )
                session.add(snapshot)
            else:
                snapshot.raw_total = raw_by_index[idx_type]
                snapshot.weighted_total = current_weighted
                snapshot.z_score = z_score
                snapshot.ewma_mean = ewma_mean
                snapshot.ewma_sigma = ewma_sigma
                snapshot.cusum_upper = cusum_upper
                snapshot.cusum_lower = cusum_lower

        await session.commit()
        print("Persisted weekly lane health and index snapshots.")

        # Attribution
        if attribution_data:
            attr = compute_attribution(attribution_data)
            print(f"\nATTRIBUTION:")
            for dim, values in attr.items():
                if values:
                    breakdown = " | ".join(f"{k}: {v:.0%}" for k, v in values.items())
                    print(f"  {dim}: {breakdown}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Advuman quant pipeline")
    parser.add_argument("--lane", default="UK-India", help="Trade lane name")
    parser.add_argument("--week", default=None, help="Week start date (YYYY-MM-DD)")
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

    if args.local:
        db_path = Path(args.sqlite_path).resolve()
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        print(f"Using local SQLite DB: {db_path}")

    week_start = date.fromisoformat(args.week) if args.week else None
    asyncio.run(run_pipeline(args.lane, week_start))
