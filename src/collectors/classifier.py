"""LLM-assisted event classification using Claude API.

Takes raw scraped content and classifies it into the 18-column event schema
using the exact delta rules from the OSINT source guides.
"""

import json
from datetime import date

from anthropic import AsyncAnthropic

from src.collectors.base import ClassifiedEvent, RawEvent
from src.config import settings
from src.db.models import (
    ConfidenceLevel,
    EventStatus,
    EventType,
    IndexType,
    Jurisdiction,
    SourceLayer,
)

CLASSIFICATION_PROMPT = """You are an OSINT analyst for Advuman, classifying trade intelligence signals for the UK-India Textiles trade lane.

Given a raw event scraped from an OSINT source, classify it into the structured 18-column format.

SOURCE CONTEXT:
- Source Name: {source_name}
- Source Layer: {source_layer}
- Primary Index: {primary_index}
- Source URL: {source_url}

RAW EVENT:
Title: {title}
Content: {content}
URL: {url}
Date: {date}

CLASSIFICATION RULES:

Event Types (pick exactly one): Regulation, FX Volatility, Port Congestion, Enforcement, Trade Remedy, Shipping Schedule, Customs, Input Price, Port Operations, Other

Jurisdiction: UK, India, or Bilateral

Event Status: Draft (proposed, may change), Announced (confirmed, not yet active), Enforced (already in effect)

Confidence Level:
- High: Official government source, verified primary data
- Medium: Industry association, carrier advisory, FX/market data
- Low: Trade press citing unnamed sources, unverified reports

RPI Delta Rules:
+1: New regulation announced, enforcement pattern change (2+ sources), customs guidance update, new certification requirement, trade remedy initiated/escalated
0: Routine reminders, unverified single-source mentions
-1: Explicit regulatory relief, trade remedy terminated

LSI Delta Rules:
+1: Port congestion advisory, blank sailing on India-UK route, dwell time increase >20%, port closure, schedule reliability deterioration
0: Normal operations, routine maintenance, single routine blank sailing
-1: Congestion resolved, capacity increase

CPI Delta Rules:
+1: INR/GBP >2% daily or >5% weekly move, input cost >10% over 3-4 weeks, tariff rate increase, freight rate >15% increase
0: FX <1% daily, input prices in normal range, rates unchanged
-1: Tariff decrease, input price collapse >15%

If the content is NOT relevant to UK-India Textiles trade, or is just noise/spam, return {{"relevant": false}}.

Return a JSON object:
{{
    "relevant": true,
    "event_type": "...",
    "jurisdiction": "...",
    "affected_object": "...",
    "event_description": "factual 1-2 sentence summary",
    "event_status": "...",
    "confidence_level": "...",
    "historical_precedent": true/false,
    "impact_pathway": "Cost/Time/Compliance/Availability (semicolon-separated if multiple)",
    "quant_metric_triggered": "description of metric",
    "index_impact": "RPI/LSI/CPI",
    "index_delta": 1/0/-1,
    "analyst_notes": "brief internal note"
}}

Return ONLY valid JSON, no markdown fences."""


async def classify_event(
    raw: RawEvent,
    source_name: str,
    source_layer: SourceLayer,
    primary_index: IndexType,
    source_url: str,
    sector: str = "Textiles",
) -> ClassifiedEvent | None:
    """Classify a raw event using Claude API.

    Returns None if the event is not relevant to the trade lane.
    """
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = CLASSIFICATION_PROMPT.format(
        source_name=source_name,
        source_layer=source_layer.value,
        primary_index=primary_index.value,
        source_url=source_url,
        title=raw.title,
        content=raw.content[:2000],  # Truncate to avoid token waste
        url=raw.url,
        date=raw.published_date or date.today(),
    )

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    data = json.loads(text)

    if not data.get("relevant", False):
        return None

    return ClassifiedEvent(
        date_observed=raw.published_date or date.today(),
        source_layer=source_layer,
        source_name=source_name,
        source_url=raw.url or source_url,
        event_type=EventType(data["event_type"]),
        jurisdiction=Jurisdiction(data["jurisdiction"]),
        sector=sector,
        affected_object=data["affected_object"],
        event_description=data["event_description"],
        event_status=EventStatus(data["event_status"]),
        confidence_level=ConfidenceLevel(data["confidence_level"]),
        historical_precedent=data["historical_precedent"],
        impact_pathway=data["impact_pathway"],
        quant_metric_triggered=data["quant_metric_triggered"],
        index_impact=IndexType(data["index_impact"]),
        index_delta=data["index_delta"],
        analyst_notes=data.get("analyst_notes", ""),
    )
