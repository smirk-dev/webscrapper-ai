"""UK Trade Remedies Authority (TRA) collector.

Source: https://www.trade-remedies.service.gov.uk/public/cases/
Method: HTTP + BeautifulSoup
Check: Weekly (Friday, 5 min)
Index: RPI (and CPI when duties imposed)
Signals: Anti-dumping investigations, safeguard measures on textile HS groups
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

TRA_URL = "https://www.trade-remedies.service.gov.uk/public/cases/"


@register("uk_tra")
class UKTRACollector(BaseCollector):
    source_name = "UK Trade Remedies Authority"
    source_url = TRA_URL
    source_layer = SourceLayer.PRIMARY
    primary_index = IndexType.RPI
    check_frequency = "weekly"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(TRA_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        # TRA lists cases in a table or list format
        for row in soup.select("tr, .case-item, .govuk-table__row"):
            cells = row.select("td, .govuk-table__cell")
            if not cells:
                continue

            text = " | ".join(c.get_text(strip=True) for c in cells)
            link_el = row.select_one("a[href]")
            href = ""
            title = text[:100]
            if link_el:
                title = link_el.get_text(strip=True)
                href = link_el.get("href", "")
                if href and not href.startswith("http"):
                    href = f"https://www.trade-remedies.service.gov.uk{href}"

            events.append(
                RawEvent(
                    title=title,
                    content=text,
                    url=href or TRA_URL,
                    published_date=date.today(),
                )
            )

        return events
