"""Lane Overview — main dashboard page.

Shows:
- Current Lane Health badge (STABLE/WATCH/ACTIVE)
- RPI / LSI / CPI current totals
- Attribution breakdown
- What Changed / What Didn't Change
"""

import asyncio
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func, select

from src.db.models import Event, HealthStatus, IndexType, LaneHealth, PipelineRun, RunStatus, TradeLane
from src.db.session import async_session

st.title("Lane Overview — UK-India Textiles")

ROOT_DIR = Path(__file__).resolve().parents[3]


def _run_script(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return result.returncode == 0, output.strip()


with st.expander("Data Refresh", expanded=False):
    st.caption("Run ingestion and lane-health recomputation directly from this page.")

    run_collectors_and_pipeline = st.button(
        "Run Collectors + Pipeline (no LLM)",
        use_container_width=True,
    )
    run_pipeline_only = st.button(
        "Run Pipeline Only",
        use_container_width=True,
    )

    if run_collectors_and_pipeline:
        with st.status("Running collectors and pipeline...", expanded=True) as status:
            ok_collect, out_collect = _run_script(
                [
                    "scripts/run_collectors.py",
                    "--all",
                    "--persist",
                    "--no-llm",
                    "--lane",
                    "UK-India",
                ]
            )
            if not ok_collect:
                status.update(label="Collector run failed", state="error")
                st.error("Collector run failed. See output below.")
                st.code("\n".join(out_collect.splitlines()[-120:]))
                st.stop()

            ok_pipe, out_pipe = _run_script(["scripts/run_pipeline.py", "--lane", "UK-India"])
            if not ok_pipe:
                status.update(label="Pipeline run failed", state="error")
                st.error("Pipeline run failed. See output below.")
                st.code("\n".join(out_pipe.splitlines()[-120:]))
                st.stop()

            status.update(label="Collectors and pipeline completed", state="complete")
            st.success("Data refresh complete.")
            st.code("\n".join(out_pipe.splitlines()[-60:]))
            st.rerun()

    if run_pipeline_only:
        with st.status("Running pipeline...", expanded=True) as status:
            ok_pipe, out_pipe = _run_script(["scripts/run_pipeline.py", "--lane", "UK-India"])
            if not ok_pipe:
                status.update(label="Pipeline run failed", state="error")
                st.error("Pipeline run failed. See output below.")
                st.code("\n".join(out_pipe.splitlines()[-120:]))
                st.stop()

            status.update(label="Pipeline completed", state="complete")
            st.success("Pipeline completed and lane health updated.")
            st.code("\n".join(out_pipe.splitlines()[-60:]))
            st.rerun()


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


async def get_run_health(window: int = 25) -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(PipelineRun)
            .join(TradeLane, PipelineRun.trade_lane_id == TradeLane.id, isouter=True)
            .where((TradeLane.name == "UK-India") | (PipelineRun.trade_lane_id.is_(None)))
            .order_by(PipelineRun.started_at.desc())
            .limit(window)
        )
        runs = list(result.scalars().all())

    total = len(runs)
    successful = sum(1 for run in runs if run.status == RunStatus.SUCCESS)
    failed = [run for run in runs if run.status == RunStatus.FAILED]
    last_run = runs[0] if runs else None
    last_failure = failed[0] if failed else None

    success_rate = (successful / total * 100.0) if total else 0.0
    return {
        "total": total,
        "success_rate": success_rate,
        "last_run_status": last_run.status.value if last_run else "no-data",
        "last_run_started_at": last_run.started_at if last_run else None,
        "last_failure_at": last_failure.started_at if last_failure else None,
    }


# Run async queries
try:
    health = asyncio.run(get_latest_health())
    events = asyncio.run(get_week_events())
    totals = asyncio.run(get_index_totals())
    run_health = asyncio.run(get_run_health())
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

st.caption("Run Health (last 25 automation runs)")
run_col1, run_col2, run_col3 = st.columns(3)
run_col1.metric("Automation Success Rate", f"{run_health['success_rate']:.0f}%")
run_col2.metric("Last Run Status", run_health["last_run_status"].upper())
run_col3.metric(
    "Last Failure",
    str(run_health["last_failure_at"]) if run_health["last_failure_at"] else "None in window",
)

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
