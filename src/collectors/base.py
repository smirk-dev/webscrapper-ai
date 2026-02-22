"""Base collector interface for all OSINT source collectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from src.db.models import (
    ConfidenceLevel,
    EventStatus,
    EventType,
    IndexType,
    Jurisdiction,
    SourceLayer,
)


@dataclass
class RawEvent:
    """Raw scraped content before LLM classification."""

    title: str
    content: str
    url: str
    published_date: date | None = None


@dataclass
class ClassifiedEvent:
    """Fully classified event matching the 18-column schema."""

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
    impact_pathway: str  # "Cost", "Time", "Compliance;Time", etc.
    quant_metric_triggered: str
    index_impact: IndexType
    index_delta: int  # +1, 0, -1
    analyst_notes: str = ""


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


class BaseCollector(ABC):
    """Abstract base for all OSINT source collectors."""

    source_name: str
    source_url: str
    source_layer: SourceLayer
    primary_index: IndexType
    check_frequency: str  # "daily" or "weekly"

    @abstractmethod
    async def collect(self) -> list[RawEvent]:
        """Fetch raw content from the OSINT source.

        Returns a list of raw events (unclassified) found since last check.
        """
        ...

    @abstractmethod
    async def parse(self, raw_html: str) -> list[RawEvent]:
        """Parse raw HTML/content into structured raw events."""
        ...
