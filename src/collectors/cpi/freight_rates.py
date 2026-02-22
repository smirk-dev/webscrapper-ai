"""Freightos Baltic Index (FBX) freight rate collector.

Source: https://fbx.freightos.com/
Method: HTTP + LLM extraction
Check: Weekly (Friday, 5 min)
Index: CPI

Delta triggers:
    +1: Freight rate increase >15% week-over-week
    0:  Stable or <10% change
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

FBX_URL = "https://fbx.freightos.com/"


@register("freight_rates")
class FreightRateCollector(BaseCollector):
    source_name = "Freightos Baltic Index (FBX)"
    source_url = FBX_URL
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
                resp = await client.get(FBX_URL)
                resp.raise_for_status()
                return await self.parse(resp.text)
            except httpx.HTTPError:
                return [
                    RawEvent(
                        title="FBX Freight Rate - Fetch Failed",
                        content="Could not reach Freightos. Manual check required.",
                        url=FBX_URL,
                        published_date=date.today(),
                    )
                ]

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        page_text = soup.get_text(separator=" ", strip=True)[:2000]

        return [
            RawEvent(
                title="FBX Weekly Freight Rate Check",
                content=page_text,
                url=FBX_URL,
                published_date=date.today(),
            )
        ]
