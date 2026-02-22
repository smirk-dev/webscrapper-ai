"""Cotton benchmark price collector.

Source: ICAC (International Cotton Advisory Committee)
Method: HTTP + LLM extraction (data may be in various formats)
Check: Weekly (Friday, 5 min)
Index: CPI

Delta triggers:
    +1: Cotlook A Index increases >10% over 3-4 weeks (sustained)
    0:  Weekly fluctuations <5%
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

ICAC_URL = "https://www.icac.org/Market-Information/Cotton-Prices"


@register("cotton")
class CottonCollector(BaseCollector):
    source_name = "Cotton Benchmark (ICAC)"
    source_url = ICAC_URL
    source_layer = SourceLayer.MARKET
    primary_index = IndexType.CPI
    check_frequency = "weekly"

    async def collect(self) -> list[RawEvent]:
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
                resp = await client.get(ICAC_URL)
                resp.raise_for_status()
                return await self.parse(resp.text)
            except httpx.HTTPError:
                return [
                    RawEvent(
                        title="Cotton Price Check - Fetch Failed",
                        content="Could not reach ICAC cotton price page. Manual check required.",
                        url=ICAC_URL,
                        published_date=date.today(),
                    )
                ]

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")

        # Extract any price-related text from the page
        page_text = soup.get_text(separator=" ", strip=True)[:2000]

        return [
            RawEvent(
                title="Cotton Weekly Price Check",
                content=page_text,
                url=ICAC_URL,
                published_date=date.today(),
            )
        ]
