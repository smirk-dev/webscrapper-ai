"""The Loadstar news collector (India coverage).

Source: https://theloadstar.com/?s=india
Method: HTTP + BeautifulSoup
Check: Daily (Afternoon, 3 min)
Index: LSI (primarily) or CPI (if cost-focused)
Note: Often reports logistics issues before official port advisories — treat as early warning.
"""

from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

LOADSTAR_SEARCH_URL = "https://theloadstar.com/?s=india"


@register("loadstar")
class LoadstarCollector(BaseCollector):
    source_name = "The Loadstar"
    source_url = LOADSTAR_SEARCH_URL
    source_layer = SourceLayer.INDUSTRY
    primary_index = IndexType.LSI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(LOADSTAR_SEARCH_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        for article in soup.select("article, .post, .search-result"):
            title_el = article.select_one("h2 a, h3 a, .entry-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            url = title_el.get("href", LOADSTAR_SEARCH_URL)

            excerpt_el = article.select_one("p, .excerpt, .entry-summary")
            content = excerpt_el.get_text(strip=True) if excerpt_el else title

            date_el = article.select_one("time, .date")
            pub_date = date.today()
            if date_el and date_el.get("datetime"):
                try:
                    pub_date = datetime.fromisoformat(
                        date_el["datetime"].replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    pass

            events.append(
                RawEvent(title=title, content=content, url=url, published_date=pub_date)
            )

        return events[:10]  # Limit to most recent 10
