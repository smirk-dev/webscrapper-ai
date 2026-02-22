"""Seed the database with UK-India Textiles trade lane and its 12 OSINT sources."""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    CheckFrequency,
    IndexType,
    LaneStatus,
    OsintSource,
    SourceLayer,
    TradeLane,
)
from src.db.session import async_session, engine


# ── Weight matrix (from Danha's sprint plan) ─────────────────────────────────

SOURCE_WEIGHTS = {
    SourceLayer.PRIMARY: 1.0,
    SourceLayer.LOGISTICS: 0.8,
    SourceLayer.MARKET: 0.7,
    SourceLayer.INDUSTRY: 0.6,
}

STATUS_WEIGHTS = {
    "Enforced": 1.0,
    "Announced": 0.7,
    "Draft": 0.4,
}

CONFIDENCE_WEIGHTS = {
    "High": 1.0,
    "Medium": 0.7,
    "Low": 0.4,
}

PRECEDENT_WEIGHTS = {
    False: 1.2,  # Novel (no precedent) — higher attention
    True: 1.0,   # Known precedent
}


# ── UK-India Textiles: 12 OSINT sources ──────────────────────────────────────

UK_INDIA_SOURCES = [
    # RPI sources (4)
    {
        "name": "DGFT (India) Notifications",
        "url": "https://dgft.gov.in/",
        "source_layer": SourceLayer.PRIMARY,
        "primary_index": IndexType.RPI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "HMRC / UK Customs Update",
        "url": "https://www.gov.uk/government/organisations/hm-revenue-customs",
        "source_layer": SourceLayer.PRIMARY,
        "primary_index": IndexType.RPI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "UKFT (UK Fashion & Textile Association)",
        "url": "https://www.ukft.org/news/",
        "source_layer": SourceLayer.INDUSTRY,
        "primary_index": IndexType.RPI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "UK Trade Remedies Authority",
        "url": "https://www.trade-remedies.service.gov.uk/public/cases/",
        "source_layer": SourceLayer.PRIMARY,
        "primary_index": IndexType.RPI,
        "check_frequency": CheckFrequency.WEEKLY,
    },
    # LSI sources (4)
    {
        "name": "JNPT (Nhava Sheva) Port Advisory",
        "url": "https://www.jnport.gov.in/",
        "source_layer": SourceLayer.LOGISTICS,
        "primary_index": IndexType.LSI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "Port of Felixstowe",
        "url": "https://www.portoffelixstowe.co.uk/operations/news/",
        "source_layer": SourceLayer.LOGISTICS,
        "primary_index": IndexType.LSI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "Carrier Service Notice (Maersk/MSC)",
        "url": "https://www.maersk.com/news/advisories",
        "source_layer": SourceLayer.LOGISTICS,
        "primary_index": IndexType.LSI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "The Loadstar",
        "url": "https://theloadstar.com/?s=india",
        "source_layer": SourceLayer.INDUSTRY,
        "primary_index": IndexType.LSI,
        "check_frequency": CheckFrequency.DAILY,
    },
    # CPI sources (4)
    {
        "name": "INR/GBP Exchange Rate (XE.com)",
        "url": "https://www.xe.com/currencycharts/?from=INR&to=GBP",
        "source_layer": SourceLayer.MARKET,
        "primary_index": IndexType.CPI,
        "check_frequency": CheckFrequency.DAILY,
    },
    {
        "name": "Cotton Benchmark (ICAC)",
        "url": "https://www.icac.org/Market-Information/Cotton-Prices",
        "source_layer": SourceLayer.MARKET,
        "primary_index": IndexType.CPI,
        "check_frequency": CheckFrequency.WEEKLY,
    },
    {
        "name": "Freightos Baltic Index (FBX)",
        "url": "https://fbx.freightos.com/",
        "source_layer": SourceLayer.MARKET,
        "primary_index": IndexType.CPI,
        "check_frequency": CheckFrequency.WEEKLY,
    },
    {
        "name": "Freight Forwarder Advisory (UK)",
        "url": "",  # No fixed URL — manually curated LinkedIn/RSS
        "source_layer": SourceLayer.INDUSTRY,
        "primary_index": IndexType.CPI,
        "check_frequency": CheckFrequency.DAILY,
    },
]


async def seed_uk_india(session: AsyncSession) -> None:
    """Create UK-India Textiles trade lane and its 12 OSINT sources."""

    # Check if already seeded
    result = await session.execute(
        select(TradeLane).where(TradeLane.name == "UK-India")
    )
    if result.scalar_one_or_none():
        print("UK-India trade lane already exists, skipping seed.")
        return

    lane = TradeLane(
        name="UK-India",
        sector="Textiles",
        status=LaneStatus.ACTIVE,
    )
    session.add(lane)
    await session.flush()  # Get lane.id

    for src_data in UK_INDIA_SOURCES:
        source = OsintSource(
            trade_lane_id=lane.id,
            name=src_data["name"],
            url=src_data["url"],
            source_layer=src_data["source_layer"],
            primary_index=src_data["primary_index"],
            check_frequency=src_data["check_frequency"],
            source_weight=SOURCE_WEIGHTS[src_data["source_layer"]],
        )
        session.add(source)

    await session.commit()
    print(f"Seeded UK-India Textiles lane with {len(UK_INDIA_SOURCES)} sources.")


async def main() -> None:
    async with async_session() as session:
        await seed_uk_india(session)


if __name__ == "__main__":
    asyncio.run(main())
