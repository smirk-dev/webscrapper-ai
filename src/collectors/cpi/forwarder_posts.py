"""Freight forwarder posts collector (manual/RSS input).

Source: LinkedIn posts from 3-5 UK forwarders with India specialization
Method: Manual input only (LinkedIn scraping violates TOS)
Check: Daily (Afternoon, 5 min)
Index: RPI or LSI (depends on content)

This collector provides a manual entry interface.
Analysts paste forwarder observations they've seen on LinkedIn/RSS.
"""

from datetime import date

from src.collectors.base import BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer


@register("forwarder_posts")
class ForwarderPostsCollector(BaseCollector):
    source_name = "Freight Forwarder Advisory (UK)"
    source_url = ""
    source_layer = SourceLayer.INDUSTRY
    primary_index = IndexType.CPI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        # This is a manual-entry source. Returns empty by default.
        # Analysts submit observations through the dashboard or CLI.
        return []

    async def parse(self, raw_html: str) -> list[RawEvent]:
        # Not applicable — manual entries bypass scraping
        return []

    @staticmethod
    def create_manual_event(
        title: str,
        content: str,
        observed_date: date | None = None,
    ) -> RawEvent:
        """Create a manual forwarder observation entry."""
        return RawEvent(
            title=title,
            content=content,
            url="",
            published_date=observed_date or date.today(),
        )
