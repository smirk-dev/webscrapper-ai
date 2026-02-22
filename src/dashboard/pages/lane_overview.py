"""Lane Overview — main dashboard page.

Shows:
- Current Lane Health badge (STABLE/WATCH/ACTIVE)
- RPI / LSI / CPI current totals
- Attribution breakdown
- What Changed / What Didn't Change
"""

import asyncio
from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func, select

from src.db.models import Event, HealthStatus, IndexType, LaneHealth, TradeLane
from src.db.session import async_session

st.title("Lane Overview — UK-India Textiles")


async def get_latest_health():
    async with async_session() as session:
        result = await session.execute(
            select(LaneHealth)
            .join(TradeLane)
            .where(TradeLane.name == "UK-India")
            .order_by(LaneHealth.week_end.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def get_week_events():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    async with async_session() as session:
        result = await session.execute(
            select(Event)
            .join(TradeLane)
            .where(TradeLane.name == "UK-India")
            .where(Event.date_observed >= week_start)
            .order_by(Event.date_observed.desc())
        )
        return result.scalars().all()


async def get_index_totals():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    async with async_session() as session:
        totals = {}
        for idx in [IndexType.RPI, IndexType.LSI, IndexType.CPI]:
            result = await session.execute(
                select(func.coalesce(func.sum(Event.index_delta), 0))
                .join(TradeLane)
                .where(TradeLane.name == "UK-India")
                .where(Event.date_observed >= week_start)
                .where(Event.index_impact == idx)
            )
            totals[idx.value] = result.scalar()
        return totals


# Run async queries
try:
    health = asyncio.run(get_latest_health())
    events = asyncio.run(get_week_events())
    totals = asyncio.run(get_index_totals())
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.info("Make sure your .env file has the correct DATABASE_URL and the database is accessible.")
    st.stop()

# ── Lane Health Badge ──
col1, col2, col3, col4 = st.columns(4)

if health:
    color_map = {
        HealthStatus.STABLE: "green",
        HealthStatus.WATCH: "orange",
        HealthStatus.ACTIVE: "red",
    }
    status = health.health_status
    col1.metric("Lane Health", status.value)
    col1.markdown(
        f'<div style="background-color:{color_map.get(status, "gray")}; '
        f'color:white; padding:10px; border-radius:5px; text-align:center; '
        f'font-size:24px; font-weight:bold;">{status.value}</div>',
        unsafe_allow_html=True,
    )
else:
    col1.metric("Lane Health", "NO DATA")
    col1.info("Run the pipeline to generate lane health data.")

# ── Index Gauges ──
col2.metric("RPI (Regulatory)", f"+{totals.get('RPI', 0)}")
col3.metric("LSI (Logistics)", f"+{totals.get('LSI', 0)}")
col4.metric("CPI (Cost)", f"+{totals.get('CPI', 0)}")

st.divider()

# ── Recent Events ──
st.subheader("This Week's Signals")

if events:
    for event in events[:10]:
        delta_icon = "🔴" if event.index_delta > 0 else ("🟢" if event.index_delta < 0 else "⚪")
        with st.expander(
            f"{delta_icon} {event.date_observed} | {event.index_impact.value} "
            f"({event.index_delta:+d}) — {event.event_description[:80]}"
        ):
            cols = st.columns(4)
            cols[0].write(f"**Source:** {event.source_name}")
            cols[1].write(f"**Type:** {event.event_type.value}")
            cols[2].write(f"**Confidence:** {event.confidence_level.value}")
            cols[3].write(f"**Status:** {event.event_status.value}")
            st.write(f"**Description:** {event.event_description}")
            st.write(f"**Impact Pathway:** {event.impact_pathway}")
            if event.analyst_notes:
                st.write(f"**Analyst Notes:** {event.analyst_notes}")
else:
    st.info("No signals collected this week. Run the collectors to populate data.")

# ── Attribution (if health data exists) ──
if health:
    st.divider()
    st.subheader("Weekly Attribution")

    fig = go.Figure(
        data=[
            go.Bar(
                name="Index Totals",
                x=["RPI", "LSI", "CPI"],
                y=[health.rpi_total, health.lsi_total, health.cpi_total],
                marker_color=["#e74c3c", "#3498db", "#2ecc71"],
            )
        ]
    )
    fig.update_layout(title="Index Contributions", yaxis_title="Delta Total", height=300)
    st.plotly_chart(fig, use_container_width=True)
