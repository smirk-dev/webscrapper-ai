"""CLI to run OSINT collectors.

Usage:
    python scripts/run_collectors.py --all
    python scripts/run_collectors.py --source hmrc
    python scripts/run_collectors.py --source hmrc felixstowe fx_inr_gbp
    python scripts/run_collectors.py --list
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import all collector modules so they register themselves
import src.collectors.rpi.dgft  # noqa: F401
import src.collectors.rpi.hmrc  # noqa: F401
import src.collectors.rpi.ukft  # noqa: F401
import src.collectors.rpi.uk_tra  # noqa: F401
import src.collectors.lsi.jnpt  # noqa: F401
import src.collectors.lsi.felixstowe  # noqa: F401
import src.collectors.lsi.carriers  # noqa: F401
import src.collectors.lsi.loadstar  # noqa: F401
import src.collectors.cpi.fx_inr_gbp  # noqa: F401
import src.collectors.cpi.cotton  # noqa: F401
import src.collectors.cpi.freight_rates  # noqa: F401
import src.collectors.cpi.forwarder_posts  # noqa: F401

from src.collectors.registry import get_collector, list_collectors
from src.collectors.base import ClassifiedEvent
from src.db.models import (
    CheckFrequency,
    ConfidenceLevel,
    Event,
    EventStatus,
    EventType,
    IndexType,
    Jurisdiction,
    LaneStatus,
    OsintSource,
    SourceLayer,
    TradeLane,
    WeightedScore,
)

SOURCE_WEIGHTS = {
    SourceLayer.PRIMARY: 1.0,
    SourceLayer.LOGISTICS: 0.8,
    SourceLayer.MARKET: 0.7,
    SourceLayer.INDUSTRY: 0.6,
}


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _heuristic_delta(index_type: IndexType, text: str) -> tuple[int, str, str, str]:
    if index_type == IndexType.RPI:
        positive = [
            "tariff",
            "duty",
            "restriction",
            "compliance",
            "inspection",
            "enforcement",
            "remedy",
            "prohibit",
            "ban",
            "customs",
        ]
        negative = [
            "relief",
            "rollback",
            "removed restriction",
            "exemption",
            "duty reduction",
            "reduced duty",
            "terminated",
        ]
        pathway = "Compliance"
        metric = "Regulatory pressure keyword heuristic"
        event_type = EventType.REGULATION.value
    elif index_type == IndexType.LSI:
        positive = [
            "congestion",
            "delay",
            "disruption",
            "closure",
            "blank sailing",
            "strike",
            "advisory",
            "diversion",
            "berth",
            "dwell",
        ]
        negative = [
            "resolved",
            "resumed",
            "cleared",
            "normal operations",
            "recovered",
            "stabilized",
        ]
        pathway = "Time"
        metric = "Logistics stress keyword heuristic"
        event_type = EventType.PORT_CONGESTION.value
    else:
        positive = [
            "increase",
            "surge",
            "rise",
            "inflation",
            "volatility",
            "higher",
            "spike",
            "up ",
            "appreciation",
            "depreciation",
        ]
        negative = [
            "decrease",
            "drop",
            "easing",
            "lower",
            "decline",
            "fell",
            "down ",
            "stabilized",
        ]
        pathway = "Cost"
        metric = "Cost pressure keyword heuristic"
        event_type = EventType.INPUT_PRICE.value

    has_positive = _contains_any(text, positive)
    has_negative = _contains_any(text, negative)

    if has_positive and not has_negative:
        delta = 1
    elif has_negative and not has_positive:
        delta = -1
    else:
        delta = 0

    return delta, event_type, pathway, metric


def _fallback_classify(raw_event, collector) -> ClassifiedEvent:
    text = f"{raw_event.title} {raw_event.content or ''}".lower()
    delta, event_type, pathway, metric = _heuristic_delta(collector.primary_index, text)
    status = EventStatus.ENFORCED if _contains_any(text, ["effective", "in force", "implemented"]) else EventStatus.ANNOUNCED
    confidence = ConfidenceLevel.HIGH if collector.source_layer in {SourceLayer.PRIMARY, SourceLayer.LOGISTICS} else ConfidenceLevel.MEDIUM

    return ClassifiedEvent(
        date_observed=raw_event.published_date or date.today(),
        source_layer=collector.source_layer,
        source_name=collector.source_name,
        source_url=raw_event.url or collector.source_url,
        event_type=EventType(event_type),
        jurisdiction=Jurisdiction.BILATERAL,
        sector="Textiles",
        affected_object="General trade lane operations",
        event_description=(raw_event.content or raw_event.title)[:400],
        event_status=status,
        confidence_level=confidence,
        historical_precedent=True,
        impact_pathway=pathway,
        quant_metric_triggered=metric,
        index_impact=collector.primary_index,
        index_delta=delta,
        analyst_notes="Keyword-heuristic fallback classification (LLM disabled/unavailable).",
    )


async def _get_or_create_source(session, collector, lane_id: int) -> OsintSource:
    from sqlalchemy import select

    result = await session.execute(
        select(OsintSource)
        .where(OsintSource.trade_lane_id == lane_id)
        .where(OsintSource.name == collector.source_name)
    )
    source = result.scalar_one_or_none()
    if source:
        return source

    source = OsintSource(
        trade_lane_id=lane_id,
        name=collector.source_name,
        url=collector.source_url,
        source_layer=collector.source_layer,
        primary_index=collector.primary_index,
        check_frequency=CheckFrequency.DAILY
        if collector.check_frequency == "daily"
        else CheckFrequency.WEEKLY,
        source_weight=SOURCE_WEIGHTS[collector.source_layer],
    )
    session.add(source)
    await session.flush()
    return source


async def _persist_events(events, collector, lane_name: str, use_llm: bool) -> int:
    from sqlalchemy import select

    from src.collectors.classifier import classify_event
    from src.config import settings
    from src.db.session import async_session
    from src.pipeline.scoring import compute_weighted_score

    async with async_session() as session:
        lane_result = await session.execute(select(TradeLane).where(TradeLane.name == lane_name))
        lane = lane_result.scalar_one_or_none()
        if lane is None:
            lane = TradeLane(name=lane_name, sector="Textiles", status=LaneStatus.ACTIVE)
            session.add(lane)
            await session.flush()

        source = await _get_or_create_source(session, collector, lane.id)
        inserted = 0

        for raw in events:
            classified = None
            if use_llm and settings.anthropic_api_key:
                try:
                    classified = await classify_event(
                        raw,
                        source_name=collector.source_name,
                        source_layer=collector.source_layer,
                        primary_index=collector.primary_index,
                        source_url=collector.source_url,
                    )
                except Exception:
                    classified = None

            if classified is None:
                classified = _fallback_classify(raw, collector)

            event = Event(
                trade_lane_id=lane.id,
                source_id=source.id,
                date_observed=classified.date_observed,
                source_layer=classified.source_layer,
                source_name=classified.source_name,
                source_url=classified.source_url,
                event_type=classified.event_type,
                jurisdiction=classified.jurisdiction,
                sector=classified.sector,
                affected_object=classified.affected_object,
                event_description=classified.event_description,
                event_status=classified.event_status,
                confidence_level=classified.confidence_level,
                historical_precedent=classified.historical_precedent,
                impact_pathway=classified.impact_pathway,
                quant_metric_triggered=classified.quant_metric_triggered,
                index_impact=classified.index_impact,
                index_delta=classified.index_delta,
                analyst_notes=classified.analyst_notes,
                reviewed=False,
            )
            session.add(event)
            await session.flush()

            score, src_w, stat_w, conf_w, prec_w = compute_weighted_score(
                delta=classified.index_delta,
                source_layer=classified.source_layer,
                event_status=classified.event_status,
                confidence_level=classified.confidence_level,
                historical_precedent=classified.historical_precedent,
            )

            session.add(
                WeightedScore(
                    event_id=event.id,
                    weighted_score=score,
                    source_weight=src_w,
                    status_weight=stat_w,
                    confidence_weight=conf_w,
                    precedent_weight=prec_w,
                )
            )
            inserted += 1

        await session.commit()
        return inserted


async def run_single(name: str, *, persist: bool, lane_name: str, use_llm: bool) -> None:


async def run_single(name: str) -> None:
    print(f"\n{'='*60}")
    print(f"Running collector: {name}")
    print(f"{'='*60}")

    collector_cls = get_collector(name)
    collector = collector_cls()

    try:
        events = await collector.collect()
        print(f"  Found {len(events)} raw event(s)")
        for i, event in enumerate(events, 1):
            print(f"  [{i}] {event.title}")
            if event.content:
                preview = event.content[:120].replace("\n", " ")
                print(f"      {preview}...")
    except Exception as e:
        print(f"  ERROR: {e}")


async def main(args: argparse.Namespace) -> None:
    if args.list:
        print("Available collectors:")
        for name in list_collectors():
            print(f"  - {name}")
        return

    if args.all:
        names = list_collectors()
    else:
        names = args.source

    if not names:
        print("No collectors specified. Use --all or --source <name>")
        return

    for name in names:
        await run_single(name)

    print(f"\nDone. Ran {len(names)} collector(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Advuman OSINT collectors")
    parser.add_argument("--all", action="store_true", help="Run all collectors")
    parser.add_argument("--source", nargs="+", default=[], help="Specific collector(s) to run")
    parser.add_argument("--list", action="store_true", help="List available collectors")
    args = parser.parse_args()
    asyncio.run(main(args))
