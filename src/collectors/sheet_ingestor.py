"""Ingest OSINT events from the analyst-maintained Google Sheets log.

Fetches a lane's tab as CSV, parses each row into the 18-column schema,
deduplicates against existing DB rows, and persists new events with
computed weighted scores.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.db.seed import SOURCE_WEIGHTS
from src.pipeline.scoring import compute_weighted_score

logger = logging.getLogger(__name__)

# ── EventType fuzzy mapping ──────────────────────────────────────────────────

EVENT_TYPE_MAP: dict[str, EventType] = {
    # Exact matches (lowercased)
    "regulation": EventType.REGULATION,
    "fx volatility": EventType.FX_VOLATILITY,
    "port congestion": EventType.PORT_CONGESTION,
    "enforcement": EventType.ENFORCEMENT,
    "trade remedy": EventType.TRADE_REMEDY,
    "shipping schedule": EventType.SHIPPING_SCHEDULE,
    "customs": EventType.CUSTOMS,
    "input price": EventType.INPUT_PRICE,
    "port operations": EventType.PORT_OPERATIONS,
    "other": EventType.OTHER,
    # Known freeform variants from the sheet
    "trade finance/export incentives": EventType.REGULATION,
    "trade finance": EventType.REGULATION,
    "export incentives": EventType.REGULATION,
    "trade policy": EventType.REGULATION,
    "daily berthing tracking": EventType.PORT_OPERATIONS,
    "berthing tracking": EventType.PORT_OPERATIONS,
    "port ops": EventType.PORT_OPERATIONS,
    "logistics intel": EventType.SHIPPING_SCHEDULE,
    "shipping sch": EventType.SHIPPING_SCHEDULE,
    "fx": EventType.FX_VOLATILITY,
    "currency": EventType.FX_VOLATILITY,
    "monetary": EventType.FX_VOLATILITY,
    "tariff": EventType.REGULATION,
    "trade remedies": EventType.TRADE_REMEDY,
    "freight rate": EventType.INPUT_PRICE,
    "freight rates": EventType.INPUT_PRICE,
    "ocean freight": EventType.INPUT_PRICE,
    "raw material": EventType.INPUT_PRICE,
    "energy": EventType.INPUT_PRICE,
    "index": EventType.INPUT_PRICE,
    "index rate": EventType.INPUT_PRICE,
    "insurance": EventType.INPUT_PRICE,
    "carrier advisory": EventType.SHIPPING_SCHEDULE,
    "port advisory": EventType.PORT_OPERATIONS,
    "congestion": EventType.PORT_CONGESTION,
    "routing": EventType.SHIPPING_SCHEDULE,
    "route change": EventType.SHIPPING_SCHEDULE,
    "security": EventType.OTHER,
    "security threat": EventType.OTHER,
}


def _map_event_type(raw: str) -> EventType:
    key = raw.strip().lower()
    if key in EVENT_TYPE_MAP:
        return EVENT_TYPE_MAP[key]
    # Substring scan
    for candidate_key, candidate_val in EVENT_TYPE_MAP.items():
        if candidate_key in key:
            return candidate_val
    logger.warning("Unknown event_type '%s', falling back to OTHER", raw)
    return EventType.OTHER


# ── Enum helpers ─────────────────────────────────────────────────────────────

def _parse_source_layer(raw: str) -> SourceLayer:
    try:
        return SourceLayer(raw.strip().title())
    except ValueError:
        logger.warning("Unknown source_layer '%s', falling back to Industry", raw)
        return SourceLayer.INDUSTRY


JURISDICTION_MAP: dict[str, Jurisdiction] = {
    "uk": Jurisdiction.UK,
    "india": Jurisdiction.INDIA,
    "vietnam": Jurisdiction.VIETNAM,
    "egypt": Jurisdiction.EGYPT,
    "bilateral": Jurisdiction.BILATERAL,
}


def _parse_jurisdiction(raw: str) -> Jurisdiction:
    key = raw.strip().lower()
    if key in JURISDICTION_MAP:
        return JURISDICTION_MAP[key]
    # Try the enum directly
    try:
        return Jurisdiction(raw.strip())
    except ValueError:
        logger.warning("Unknown jurisdiction '%s', falling back to Bilateral", raw)
        return Jurisdiction.BILATERAL


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"yes", "y", "true", "1"}


def _parse_severity(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        val = int(raw)
        if val not in (1, 2, 3):
            logger.warning("Severity '%s' not in 1/2/3, storing as-is", raw)
        return val
    except ValueError:
        return None


# ── Row hash for deduplication ───────────────────────────────────────────────

def _compute_row_hash(
    date_observed: date,
    source_name: str,
    index_impact: IndexType,
    index_delta: int,
    event_description: str,
) -> str:
    key = (
        f"{date_observed.isoformat()}|"
        f"{source_name.strip().lower()}|"
        f"{index_impact.value}|"
        f"{index_delta}|"
        f"{event_description.strip()[:100]}"
    )
    return hashlib.sha256(key.encode()).hexdigest()


# ── Parsed row dataclass ────────────────────────────────────────────────────

@dataclass
class SheetRow:
    date_observed: date
    source_layer: SourceLayer
    source_name: str
    source_url: str
    event_type: EventType
    jurisdiction: Jurisdiction
    sector: str
    affected_object: str
    event_description: str
    event_status: EventStatus
    confidence_level: ConfidenceLevel
    historical_precedent: bool
    impact_pathway: str
    quant_metric_triggered: str
    index_impact: IndexType
    index_delta: int
    analyst_notes: str
    reviewed: bool
    severity: int | None
    row_hash: str


# ── Header detection ────────────────────────────────────────────────────────

def _is_header_row(first_val: str) -> bool:
    try:
        datetime.strptime(first_val.strip(), "%d/%m/%Y")
        return False
    except ValueError:
        return True


# ── CSV row parser ──────────────────────────────────────────────────────────

def parse_rows(csv_text: str) -> tuple[list[SheetRow], list[str]]:
    """Parse CSV text into SheetRow objects.

    Returns (valid_rows, error_messages).
    """
    rows: list[SheetRow] = []
    errors: list[str] = []

    reader = csv.reader(io.StringIO(csv_text))
    all_rows = list(reader)

    if not all_rows:
        return rows, errors

    start = 1 if _is_header_row(all_rows[0][0]) else 0

    for i, cols in enumerate(all_rows[start:], start=start + 1):
        # Skip empty rows
        if not cols or all(c.strip() == "" for c in cols):
            continue

        # Skip rows where the date cell is empty (trailing blank rows, instruction rows)
        if not cols[0].strip():
            continue

        if len(cols) < 16:
            errors.append(f"Row {i}: too few columns ({len(cols)})")
            continue

        try:
            date_observed = datetime.strptime(cols[0].strip(), "%d/%m/%Y").date()
        except ValueError:
            # Skip known non-data rows (headers, instructions) silently
            if _is_header_row(cols[0]):
                continue
            errors.append(f"Row {i}: invalid date '{cols[0].strip()}'")
            continue

        source_layer = _parse_source_layer(cols[1])
        source_name = cols[2].strip()
        source_url = cols[3].strip()
        event_type = _map_event_type(cols[4])
        jurisdiction = _parse_jurisdiction(cols[5])
        sector = cols[6].strip() or "General"
        affected_object = cols[7].strip() or "General trade lane operations"
        event_description = cols[8].strip()

        if not event_description:
            errors.append(f"Row {i}: empty event_description")
            continue

        # Required enum fields — skip row on failure
        try:
            event_status = EventStatus(cols[9].strip().title())
        except ValueError:
            errors.append(f"Row {i}: invalid event_status '{cols[9].strip()}'")
            continue

        try:
            confidence_level = ConfidenceLevel(cols[10].strip().title())
        except ValueError:
            errors.append(f"Row {i}: invalid confidence_level '{cols[10].strip()}'")
            continue

        historical_precedent = _parse_bool(cols[11])
        impact_pathway = cols[12].strip() or "Cost"
        quant_metric_triggered = cols[13].strip() or ""

        try:
            index_impact = IndexType(cols[14].strip().upper())
        except ValueError:
            errors.append(f"Row {i}: invalid index_impact '{cols[14].strip()}'")
            continue

        try:
            index_delta = int(cols[15].strip())
        except ValueError:
            errors.append(f"Row {i}: invalid index_delta '{cols[15].strip()}'")
            continue

        analyst_notes = cols[16].strip() if len(cols) > 16 else ""
        reviewed = _parse_bool(cols[17]) if len(cols) > 17 else False
        severity = _parse_severity(cols[18]) if len(cols) > 18 else None

        row_hash = _compute_row_hash(
            date_observed, source_name, index_impact, index_delta, event_description
        )

        rows.append(SheetRow(
            date_observed=date_observed,
            source_layer=source_layer,
            source_name=source_name,
            source_url=source_url,
            event_type=event_type,
            jurisdiction=jurisdiction,
            sector=sector,
            affected_object=affected_object,
            event_description=event_description,
            event_status=event_status,
            confidence_level=confidence_level,
            historical_precedent=historical_precedent,
            impact_pathway=impact_pathway,
            quant_metric_triggered=quant_metric_triggered,
            index_impact=index_impact,
            index_delta=index_delta,
            analyst_notes=analyst_notes,
            reviewed=reviewed,
            severity=severity,
            row_hash=row_hash,
        ))

    return rows, errors


# ── DB helpers ──────────────────────────────────────────────────────────────

LANE_SECTOR_MAP = {
    "UK-India": "Textiles",
    "UK-Egypt": "Scrap Metal",
    "UK-Vietnam": "General",
}


async def _get_or_create_lane(session: AsyncSession, lane_name: str) -> TradeLane:
    result = await session.execute(
        select(TradeLane).where(TradeLane.name == lane_name)
    )
    lane = result.scalar_one_or_none()
    if lane:
        return lane

    sector = LANE_SECTOR_MAP.get(lane_name, "General")
    lane = TradeLane(name=lane_name, sector=sector, status=LaneStatus.ACTIVE)
    session.add(lane)
    await session.flush()
    return lane


async def _find_or_create_source(
    session: AsyncSession,
    lane_id: int,
    source_name: str,
    source_url: str,
    source_layer: SourceLayer,
    index_impact: IndexType,
) -> OsintSource:
    result = await session.execute(
        select(OsintSource)
        .where(OsintSource.trade_lane_id == lane_id)
        .where(OsintSource.name == source_name)
    )
    source = result.scalar_one_or_none()
    if source:
        if source_url:
            source.url = source_url
        return source

    source = OsintSource(
        trade_lane_id=lane_id,
        name=source_name,
        url=source_url or "",
        source_layer=source_layer,
        primary_index=index_impact,
        check_frequency=CheckFrequency.DAILY,
        source_weight=SOURCE_WEIGHTS[source_layer],
    )
    session.add(source)
    await session.flush()
    return source


# ── Main ingestor ───────────────────────────────────────────────────────────

class SheetIngestor:
    """Fetch, parse, deduplicate, and persist events from a Google Sheet tab."""

    def __init__(self, lane_name: str, dry_run: bool = False):
        self.lane_name = lane_name
        self.dry_run = dry_run

    async def fetch_csv(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    async def ingest(self, csv_url: str) -> dict:
        """Fetch → parse → deduplicate → persist. Returns stats dict."""
        from src.db.session import async_session

        stats = {
            "fetched": 0,
            "skipped_parse_error": 0,
            "skipped_duplicate": 0,
            "inserted": 0,
        }

        csv_text = await self.fetch_csv(csv_url)
        parsed_rows, errors = parse_rows(csv_text)
        stats["fetched"] = len(parsed_rows) + len(errors)
        stats["skipped_parse_error"] = len(errors)
        for err in errors:
            print(f"  [PARSE ERROR] {err}")

        if not parsed_rows:
            return stats

        async with async_session() as session:
            lane = await _get_or_create_lane(session, self.lane_name)

            # Bulk deduplication
            candidate_hashes = {row.row_hash for row in parsed_rows}
            result = await session.execute(
                select(Event.sheet_row_hash).where(
                    Event.sheet_row_hash.in_(candidate_hashes)
                )
            )
            existing_hashes = {r for (r,) in result.all()}
            new_rows = [r for r in parsed_rows if r.row_hash not in existing_hashes]
            stats["skipped_duplicate"] = len(parsed_rows) - len(new_rows)

            if self.dry_run:
                stats["inserted"] = len(new_rows)
                print(f"  [DRY RUN] Would insert {len(new_rows)} rows")
                return stats

            # Source cache: lowered name → OsintSource
            source_cache: dict[str, OsintSource] = {}

            for row in new_rows:
                cache_key = row.source_name.strip().lower()
                if cache_key not in source_cache:
                    source_cache[cache_key] = await _find_or_create_source(
                        session,
                        lane.id,
                        row.source_name,
                        row.source_url,
                        row.source_layer,
                        row.index_impact,
                    )
                source = source_cache[cache_key]

                event = Event(
                    trade_lane_id=lane.id,
                    source_id=source.id,
                    date_observed=row.date_observed,
                    source_layer=row.source_layer,
                    source_name=row.source_name,
                    source_url=row.source_url,
                    event_type=row.event_type,
                    jurisdiction=row.jurisdiction,
                    sector=row.sector,
                    affected_object=row.affected_object,
                    event_description=row.event_description,
                    event_status=row.event_status,
                    confidence_level=row.confidence_level,
                    historical_precedent=row.historical_precedent,
                    impact_pathway=row.impact_pathway,
                    quant_metric_triggered=row.quant_metric_triggered,
                    index_impact=row.index_impact,
                    index_delta=row.index_delta,
                    analyst_notes=row.analyst_notes or None,
                    reviewed=row.reviewed,
                    severity=row.severity,
                    sheet_row_hash=row.row_hash,
                )
                session.add(event)
                await session.flush()

                score, src_w, stat_w, conf_w, prec_w = compute_weighted_score(
                    delta=row.index_delta,
                    source_layer=row.source_layer,
                    event_status=row.event_status,
                    confidence_level=row.confidence_level,
                    historical_precedent=row.historical_precedent,
                )
                session.add(WeightedScore(
                    event_id=event.id,
                    weighted_score=score,
                    source_weight=src_w,
                    status_weight=stat_w,
                    confidence_weight=conf_w,
                    precedent_weight=prec_w,
                ))
                stats["inserted"] += 1

            await session.commit()

        return stats
