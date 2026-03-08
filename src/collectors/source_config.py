"""Dynamic collector source configuration loaded from CSV (e.g. Google Sheets)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class SourceOverride:
    """Optional runtime overrides for a registered collector."""

    collector: str
    enabled: bool = True
    source_name: str | None = None
    source_url: str | None = None
    scrape_url: str | None = None
    check_frequency: str | None = None


def _clean_value(value: Any) -> str:
    return str(value or "").strip()


def _parse_bool(value: Any, default: bool = True) -> bool:
    raw = _clean_value(value).lower()
    if raw == "":
        return default
    if raw in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _normalize_frequency(value: Any) -> str | None:
    raw = _clean_value(value).lower()
    if raw in {"daily", "day", "d"}:
        return "daily"
    if raw in {"weekly", "week", "w"}:
        return "weekly"
    return None


def parse_source_overrides(rows: list[dict[str, Any]]) -> dict[str, SourceOverride]:
    """Normalize CSV rows into collector-keyed overrides.

    Required column: collector
    Optional columns: enabled, source_name, source_url, scrape_url, check_frequency
    """

    overrides: dict[str, SourceOverride] = {}

    for row in rows:
        collector = _clean_value(
            row.get("collector") or row.get("source") or row.get("name")
        ).lower()
        if not collector:
            continue

        overrides[collector] = SourceOverride(
            collector=collector,
            enabled=_parse_bool(row.get("enabled"), default=True),
            source_name=_clean_value(row.get("source_name")) or None,
            source_url=_clean_value(row.get("source_url")) or None,
            scrape_url=_clean_value(row.get("scrape_url")) or None,
            check_frequency=_normalize_frequency(row.get("check_frequency")),
        )

    return overrides


async def load_source_overrides(csv_location: str) -> dict[str, SourceOverride]:
    """Load source overrides from a URL or local CSV file path."""

    location = (csv_location or "").strip()
    if not location:
        return {}

    if location.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(location)
            resp.raise_for_status()
            text = resp.text
    else:
        text = Path(location).read_text(encoding="utf-8")

    reader = csv.DictReader(text.splitlines())
    return parse_source_overrides(list(reader))
