"""Signal Log — filterable table of all OSINT events.

Matches the 18-column Excel framework.
"""

import asyncio
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import select

from src.db.models import (
    ConfidenceLevel,
    Event,
    EventType,
    IndexType,
    TradeLane,
)
from src.db.session import async_session

st.title("Signal Log — UK-India Textiles")

# ── Filters ──
col1, col2, col3, col4 = st.columns(4)

with col1:
    days_back = st.selectbox("Time Range", [7, 14, 30, 90], index=0)
with col2:
    index_filter = st.multiselect(
        "Index", [i.value for i in IndexType], default=[i.value for i in IndexType]
    )
with col3:
    type_filter = st.multiselect("Event Type", [t.value for t in EventType], default=[])
with col4:
    confidence_filter = st.multiselect(
        "Confidence", [c.value for c in ConfidenceLevel], default=[]
    )

reviewed_only = st.checkbox("Show reviewed only", value=False)


async def get_events():
    start_date = date.today() - timedelta(days=days_back)
    async with async_session() as session:
        query = (
            select(Event)
            .join(TradeLane)
            .where(TradeLane.name == "UK-India")
            .where(Event.date_observed >= start_date)
        )
        if index_filter:
            query = query.where(Event.index_impact.in_([IndexType(v) for v in index_filter]))
        if type_filter:
            query = query.where(Event.event_type.in_([EventType(v) for v in type_filter]))
        if confidence_filter:
            query = query.where(
                Event.confidence_level.in_([ConfidenceLevel(v) for v in confidence_filter])
            )
        if reviewed_only:
            query = query.where(Event.reviewed.is_(True))

        query = query.order_by(Event.date_observed.desc())
        result = await session.execute(query)
        return result.scalars().all()


try:
    events = asyncio.run(get_events())
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if events:
    data = []
    for e in events:
        data.append({
            "Date": e.date_observed,
            "Source": e.source_name,
            "Type": e.event_type.value,
            "Jurisdiction": e.jurisdiction.value,
            "Description": e.event_description[:100],
            "Status": e.event_status.value,
            "Confidence": e.confidence_level.value,
            "Precedent": "Yes" if e.historical_precedent else "No",
            "Pathway": e.impact_pathway,
            "Index": e.index_impact.value,
            "Delta": e.index_delta,
            "Reviewed": "Yes" if e.reviewed else "No",
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, height=500)

    # Export
    csv = df.to_csv(index=False)
    st.download_button("Download CSV", csv, "advuman_signals.csv", "text/csv")
else:
    st.info("No signals found for the selected filters.")
