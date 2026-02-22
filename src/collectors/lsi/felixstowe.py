"""Port of Felixstowe operations news collector.

Source: https://www.portoffelixstowe.co.uk/operations/news/
Method: HTTP + BeautifulSoup (simple HTML)
Check: Daily (Morning, 3 min)
Index: LSI

Signals: Port congestion advisory, operational disruption
Baseline: "Normal operations" logged as delta=0 (used in "What Did Not Change")
"""

from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

FELIXSTOWE_URL = "https://www.portoffelixstowe.co.uk/operations/news/"


@register("felixstowe")
class FelixstoweCollector(BaseCollector):
    source_name = "Port of Felixstowe"
    source_url = FELIXSTOWE_URL
    source_layer = SourceLayer.LOGISTICS
    primary_index = IndexType.LSI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(FELIXSTOWE_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        # Look for news article links/items on the page
        for article in soup.select("article, .news-item, .post-item, li.item"):
            title_el = article.select_one("h2, h3, .title, a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "") if title_el.name == "a" else ""
            if not link:
                link_el = article.select_one("a")
                link = link_el.get("href", "") if link_el else ""

            if link and not link.startswith("http"):
                link = f"https://www.portoffelixstowe.co.uk{link}"

            content_el = article.select_one("p, .excerpt, .summary")
            content = content_el.get_text(strip=True) if content_el else title

            date_el = article.select_one("time, .date, .meta")
            pub_date = None
            if date_el:
                dt_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
                try:
                    pub_date = datetime.fromisoformat(
                        dt_str.replace("Z", "+00:00")
                    ).date()
                except (ValueError, AttributeError):
                    pub_date = date.today()

            events.append(
                RawEvent(
                    title=title,
                    content=content,
                    url=link or FELIXSTOWE_URL,
                    published_date=pub_date or date.today(),
                )
            )

        # If no articles found, log baseline check
        if not events:
            events.append(
                RawEvent(
                    title="Port of Felixstowe - No Updates",
                    content="No operational news items found. Baseline confirmed.",
                    url=FELIXSTOWE_URL,
                    published_date=date.today(),
                )
            )

        return events
