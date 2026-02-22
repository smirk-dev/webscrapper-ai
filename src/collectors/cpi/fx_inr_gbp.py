"""INR/GBP exchange rate collector.

Source: XE.com currency charts
Method: HTTP scraping for rate data
Check: Daily (Afternoon, 3 min)
Index: CPI

Delta triggers:
    +1: INR/GBP moves >2% in single day OR >5% over 1 week
    0:  Daily movement <1% (normal volatility)
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

XE_URL = "https://www.xe.com/currencyconverter/convert/?Amount=1&From=INR&To=GBP"


@register("fx_inr_gbp")
class FXINRGBPCollector(BaseCollector):
    source_name = "INR/GBP Exchange Rate (XE.com)"
    source_url = "https://www.xe.com/currencycharts/?from=INR&to=GBP"
    source_layer = SourceLayer.MARKET
    primary_index = IndexType.CPI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            resp = await client.get(XE_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")

        # XE embeds the conversion result in a <p> with class containing "result"
        rate_text = ""
        rate_el = soup.find("p", class_=lambda c: c and "result" in c.lower()) if soup else None
        if rate_el:
            rate_text = rate_el.get_text(strip=True)

        if not rate_text:
            # Fallback: look for any element containing the rate pattern
            for el in soup.find_all(string=lambda s: s and "GBP" in s and "INR" in s):
                rate_text = el.strip()
                break

        if not rate_text:
            rate_text = "Rate data unavailable — manual check required"

        return [
            RawEvent(
                title="INR/GBP Daily Rate Check",
                content=rate_text,
                url=self.source_url,
                published_date=date.today(),
            )
        ]
