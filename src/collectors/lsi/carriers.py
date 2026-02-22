"""Carrier service advisory collector (Maersk/MSC).

Source: https://www.maersk.com/news/advisories
Method: HTTP + BeautifulSoup
Check: Daily (Morning, 3 min)
Index: LSI
Signals: Blank sailings on India-UK route, service disruptions
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

MAERSK_ADVISORIES_URL = "https://www.maersk.com/news/advisories"


@register("carriers")
class CarrierCollector(BaseCollector):
    source_name = "Carrier Service Notice (Maersk/MSC)"
    source_url = MAERSK_ADVISORIES_URL
    source_layer = SourceLayer.LOGISTICS
    primary_index = IndexType.LSI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        events = []
        events.extend(await self._collect_maersk())
        return events

    async def _collect_maersk(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            try:
                resp = await client.get(MAERSK_ADVISORIES_URL)
                resp.raise_for_status()
                return await self.parse(resp.text)
            except httpx.HTTPError:
                return [
                    RawEvent(
                        title="Maersk Advisories - Fetch Failed",
                        content="Could not reach Maersk advisory page. Manual check required.",
                        url=MAERSK_ADVISORIES_URL,
                        published_date=date.today(),
                    )
                ]

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        for article in soup.select("article, .advisory-item, .news-card, .list-item"):
            title_el = article.select_one("h2, h3, a, .title")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = ""
            if title_el.name == "a":
                href = title_el.get("href", "")
            else:
                link_el = article.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

            if href and not href.startswith("http"):
                href = f"https://www.maersk.com{href}"

            content_el = article.select_one("p, .description, .excerpt")
            content = content_el.get_text(strip=True) if content_el else title

            # Filter for India/UK relevance
            combined = f"{title} {content}".lower()
            if any(kw in combined for kw in ["india", "uk", "europe", "blank", "service change"]):
                events.append(
                    RawEvent(
                        title=title,
                        content=content,
                        url=href or MAERSK_ADVISORIES_URL,
                        published_date=date.today(),
                    )
                )

        return events
