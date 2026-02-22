"""DGFT (Directorate General of Foreign Trade, India) collector.

Source: https://dgft.gov.in/
Method: HTTP + BeautifulSoup
Check: Daily (Morning, 5 min)
Index: RPI
Keywords: 'Export', 'Textiles', 'HS 50-63', 'Documentation', 'Certificate', 'Amendment'
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

DGFT_NOTIFICATIONS_URL = "https://dgft.gov.in/CP/?opt=notification"


@register("dgft")
class DGFTCollector(BaseCollector):
    source_name = "DGFT (India) Notifications"
    source_url = "https://dgft.gov.in/"
    source_layer = SourceLayer.PRIMARY
    primary_index = IndexType.RPI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            resp = await client.get(DGFT_NOTIFICATIONS_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        # DGFT typically lists notifications in a table or list
        for row in soup.select("table tr, .notification-item, .views-row"):
            cells = row.select("td")
            if len(cells) >= 2:
                title = cells[0].get_text(strip=True)
                link_el = row.select_one("a[href]")
                url = ""
                if link_el:
                    href = link_el.get("href", "")
                    url = href if href.startswith("http") else f"https://dgft.gov.in{href}"

                content = " | ".join(c.get_text(strip=True) for c in cells)
                events.append(
                    RawEvent(
                        title=title or "DGFT Notification",
                        content=content,
                        url=url or self.source_url,
                        published_date=date.today(),
                    )
                )

        # Fallback: check for any links with notification-like text
        if not events:
            for link in soup.select("a[href]"):
                text = link.get_text(strip=True).lower()
                if any(kw in text for kw in ["notification", "circular", "public notice"]):
                    href = link.get("href", "")
                    full_url = href if href.startswith("http") else f"https://dgft.gov.in{href}"
                    events.append(
                        RawEvent(
                            title=link.get_text(strip=True),
                            content=link.get_text(strip=True),
                            url=full_url,
                            published_date=date.today(),
                        )
                    )

        return events
