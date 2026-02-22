"""UKFT (UK Fashion & Textile Association) news collector.

Source: https://www.ukft.org/news/
Method: HTTP + BeautifulSoup
Check: Daily (Afternoon, 3 min)
Index: RPI
Signals: Enforcement mentions, labelling compliance, import inspection changes
"""

from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

UKFT_URL = "https://www.ukft.org/news/"


@register("ukft")
class UKFTCollector(BaseCollector):
    source_name = "UKFT (UK Fashion & Textile Association)"
    source_url = UKFT_URL
    source_layer = SourceLayer.INDUSTRY
    primary_index = IndexType.RPI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(UKFT_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        for article in soup.select("article, .post, .news-item, .entry"):
            title_el = article.select_one("h2 a, h3 a, .entry-title a, a.title")
            if not title_el:
                title_el = article.select_one("h2, h3, .entry-title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "") if title_el.name == "a" else ""
            url = href if href.startswith("http") else UKFT_URL

            excerpt_el = article.select_one("p, .excerpt, .entry-summary")
            content = excerpt_el.get_text(strip=True) if excerpt_el else title

            date_el = article.select_one("time, .date, .published")
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

        return events
