"""JNPT (Jawaharlal Nehru Port Trust) collector.

Source: https://www.jnport.gov.in/
Method: Playwright (JS-heavy site, needs browser automation)
Check: Daily (Morning, 3 min)
Index: LSI
Note: Homepage banner only — don't deep-dive PDFs (per OSINT guide)
"""

from datetime import date

import httpx
from bs4 import BeautifulSoup

from src.collectors.base import DEFAULT_HEADERS, BaseCollector, RawEvent
from src.collectors.registry import register
from src.db.models import IndexType, SourceLayer

JNPT_URL = "https://www.jnport.gov.in/"


@register("jnpt")
class JNPTCollector(BaseCollector):
    source_name = "JNPT (Nhava Sheva) Port Advisory"
    source_url = JNPT_URL
    source_layer = SourceLayer.LOGISTICS
    primary_index = IndexType.LSI
    check_frequency = "daily"

    async def collect(self) -> list[RawEvent]:
        # Try basic HTTP first; fall back to Playwright if JS-rendered
        try:
            return await self._collect_http()
        except Exception:
            return await self._collect_playwright()

    async def _collect_http(self) -> list[RawEvent]:
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS
        ) as client:
            resp = await client.get(JNPT_URL)
            resp.raise_for_status()
            return await self.parse(resp.text)

    async def _collect_playwright(self) -> list[RawEvent]:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(JNPT_URL, wait_until="domcontentloaded", timeout=30000)
                html = await page.content()
                await browser.close()
                return await self.parse(html)
        except ImportError:
            return [
                RawEvent(
                    title="JNPT - Collection Failed",
                    content="Playwright not installed. Install with: playwright install chromium",
                    url=JNPT_URL,
                    published_date=date.today(),
                )
            ]

    async def parse(self, raw_html: str) -> list[RawEvent]:
        soup = BeautifulSoup(raw_html, "lxml")
        events = []

        # Look for banner notices, alerts, marquee text, or news tickers
        for el in soup.select(
            ".banner, .notice, .alert, marquee, .news-ticker, "
            ".announcement, .highlight, .scroll-text"
        ):
            text = el.get_text(strip=True)
            if text and len(text) > 10:
                events.append(
                    RawEvent(
                        title="JNPT Port Advisory",
                        content=text[:500],
                        url=JNPT_URL,
                        published_date=date.today(),
                    )
                )

        # Also check for any linked PDFs about operations
        for link in soup.select("a[href$='.pdf']"):
            text = link.get_text(strip=True)
            if any(kw in text.lower() for kw in ["advisory", "congestion", "notice", "operation"]):
                href = link.get("href", "")
                full_url = href if href.startswith("http") else f"https://www.jnport.gov.in{href}"
                events.append(
                    RawEvent(
                        title=text,
                        content=f"PDF advisory: {text}",
                        url=full_url,
                        published_date=date.today(),
                    )
                )

        if not events:
            events.append(
                RawEvent(
                    title="JNPT - No Advisories",
                    content="No port advisories or congestion notices found on homepage.",
                    url=JNPT_URL,
                    published_date=date.today(),
                )
            )

        return events
