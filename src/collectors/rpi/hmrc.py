"""HMRC / UK Customs collector.

Source: https://www.gov.uk/government/organisations/hm-revenue-customs
Method: HTTP + BeautifulSoup (GOV.UK has clean, well-structured HTML)
Check: Daily (Morning, 5 min)
Index: RPI
Keywords: 'India', 'textiles', 'HS 50-63', 'commodity codes', 'customs'
"""

from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

HMRC_SEARCH_URL = (
    "https://www.gov.uk/search/all"
    "?keywords=textiles+india+customs"
    "&organisations%5B%5D=hm-revenue-customs"
    "&order=updated-newest"
)


@register("hmrc")
class HMRCCollector(BaseCollector):
    source_name = "HMRC / UK Customs Update"
    source_url = "https://www.gov.uk/government/organisations/hm-revenue-customs"
    source_layer = SourceLayer.PRIMARY
    primary_index = IndexType.RPI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(HMRC_SEARCH_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        for result in soup.select("li.gem-c-document-list__item"):
            link_el = result.select_one("a.gem-c-document-list__item-title")
            if not link_el:
                continue

            title = link_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = f"https://www.gov.uk{href}" if href.startswith("/") else href

            desc_el = result.select_one(".gem-c-document-list__item-description")
            description = desc_el.get_text(strip=True) if desc_el else ""

            meta_el = result.select_one(".gem-c-document-list__attribute time")
            pub_date = None
            if meta_el and meta_el.get("datetime"):
                try:
                    pub_date = datetime.fromisoformat(
                        meta_el["datetime"].replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    pub_date = date.today()

            events.append(
                RawEvent(
                    title=title,
                    content=description,
                    url=url,
                    published_date=pub_date,
                )
            )

        return events
