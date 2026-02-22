"""CLI to run the quant pipeline on collected events.

Usage:
    python scripts/run_pipeline.py --lane uk-india
    python scripts/run_pipeline.py --lane uk-india --week 2026-02-17
"""

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from src.db.models import Event, IndexType, TradeLane
from src.db.session import async_session
from src.pipeline.attribution import compute_attribution
from src.pipeline.rollup import compute_lane_health
from src.pipeline.scoring import compute_weighted_score


async def run_pipeline(lane_name: str, week_start: date | None = None) -> None:
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
            print("No events found for this week.")
            return

        print(f"Found {len(events)} events\n")

        # Compute weighted scores
        rpi_total = 0.0
        lsi_total = 0.0
        cpi_total = 0.0
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
            elif event.index_impact == IndexType.LSI:
                lsi_total += event.index_delta
            elif event.index_impact == IndexType.CPI:
                cpi_total += event.index_delta

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
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week) if args.week else None
    asyncio.run(run_pipeline(args.lane, week_start))
