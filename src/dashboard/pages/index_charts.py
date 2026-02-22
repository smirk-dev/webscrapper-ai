"""Index Charts — time series visualization of RPI/LSI/CPI.

Shows:
- Raw index totals over time
- EWMA baseline overlay
- Z-score deviation chart
- CUSUM chart with threshold lines
- Lane Health history
"""

import asyncio
from datetime import date, timedelta

import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from src.db.models import IndexSnapshot, IndexType, LaneHealth, TradeLane
from src.db.session import async_session

st.title("Index Charts — UK-India Textiles")

days_range = st.slider("Days to show", 7, 180, 60)


async def get_snapshots():
    start = date.today() - timedelta(days=days_range)
    async with async_session() as session:
        result = await session.execute(
            select(IndexSnapshot)
            .join(TradeLane)
            .where(TradeLane.name == "UK-India")
            .where(IndexSnapshot.date >= start)
            .order_by(IndexSnapshot.date)
        )
        return result.scalars().all()


async def get_health_history():
    start = date.today() - timedelta(days=days_range)
    async with async_session() as session:
        result = await session.execute(
            select(LaneHealth)
            .join(TradeLane)
            .where(TradeLane.name == "UK-India")
            .where(LaneHealth.week_start >= start)
            .order_by(LaneHealth.week_start)
        )
        return result.scalars().all()


try:
    snapshots = asyncio.run(get_snapshots())
    health_history = asyncio.run(get_health_history())
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

if not snapshots:
    st.info("No index data available. Run the pipeline to generate index snapshots.")
    st.stop()

# ── Raw Index Totals ──
st.subheader("Index Totals Over Time")

colors = {"RPI": "#e74c3c", "LSI": "#3498db", "CPI": "#2ecc71"}
fig = go.Figure()

for idx_type in [IndexType.RPI, IndexType.LSI, IndexType.CPI]:
    filtered = [s for s in snapshots if s.index_type == idx_type]
    if filtered:
        fig.add_trace(
            go.Scatter(
                x=[s.date for s in filtered],
                y=[s.weighted_total for s in filtered],
                name=idx_type.value,
                line=dict(color=colors[idx_type.value]),
            )
        )

fig.update_layout(height=400, yaxis_title="Weighted Total")
st.plotly_chart(fig, use_container_width=True)

# ── Z-Score Deviation ──
st.subheader("Z-Score Deviation from Baseline")

fig_z = go.Figure()
for idx_type in [IndexType.RPI, IndexType.LSI, IndexType.CPI]:
    filtered = [s for s in snapshots if s.index_type == idx_type and s.z_score is not None]
    if filtered:
        fig_z.add_trace(
            go.Scatter(
                x=[s.date for s in filtered],
                y=[s.z_score for s in filtered],
                name=idx_type.value,
                line=dict(color=colors[idx_type.value]),
            )
        )

# Add threshold lines
fig_z.add_hline(y=2.0, line_dash="dash", line_color="red", annotation_text="+2σ")
fig_z.add_hline(y=-2.0, line_dash="dash", line_color="red", annotation_text="-2σ")
fig_z.add_hline(y=0, line_dash="dot", line_color="gray")
fig_z.update_layout(height=400, yaxis_title="Z-Score (σ)")
st.plotly_chart(fig_z, use_container_width=True)

# ── CUSUM ──
st.subheader("CUSUM — Persistent Shift Detection (RPI)")

rpi_snapshots = [s for s in snapshots if s.index_type == IndexType.RPI and s.cusum_upper is not None]
if rpi_snapshots:
    fig_c = go.Figure()
    fig_c.add_trace(
        go.Scatter(
            x=[s.date for s in rpi_snapshots],
            y=[s.cusum_upper for s in rpi_snapshots],
            name="C⁺ (Upper)",
            line=dict(color="#e74c3c"),
        )
    )
    fig_c.add_trace(
        go.Scatter(
            x=[s.date for s in rpi_snapshots],
            y=[s.cusum_lower for s in rpi_snapshots],
            name="C⁻ (Lower)",
            line=dict(color="#3498db"),
        )
    )
    fig_c.add_hline(y=4.5, line_dash="dash", line_color="red", annotation_text="h=4.5 (alarm)")
    fig_c.add_hline(y=-4.5, line_dash="dash", line_color="red")
    fig_c.update_layout(height=350, yaxis_title="CUSUM Statistic")
    st.plotly_chart(fig_c, use_container_width=True)
else:
    st.info("No CUSUM data available yet.")

# ── Lane Health History ──
st.subheader("Lane Health History")

if health_history:
    health_colors = {"STABLE": "#2ecc71", "WATCH": "#f39c12", "ACTIVE": "#e74c3c"}
    fig_h = go.Figure()
    fig_h.add_trace(
        go.Bar(
            x=[h.week_start for h in health_history],
            y=[h.combined_total for h in health_history],
            marker_color=[health_colors.get(h.health_status.value, "gray") for h in health_history],
            text=[h.health_status.value for h in health_history],
            textposition="outside",
        )
    )
    fig_h.add_hline(y=4, line_dash="dash", line_color="orange", annotation_text="WATCH threshold")
    fig_h.add_hline(y=8, line_dash="dash", line_color="red", annotation_text="ACTIVE threshold")
    fig_h.update_layout(height=350, yaxis_title="Combined Total", xaxis_title="Week")
    st.plotly_chart(fig_h, use_container_width=True)
else:
    st.info("No lane health history available.")
