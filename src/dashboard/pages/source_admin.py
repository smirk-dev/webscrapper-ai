"""Source Admin page.

Displays loaded source config from Google Sheets and effective runtime settings
that will be used by collector runs.
"""

import asyncio

import pandas as pd
import streamlit as st

# Import collector modules so registry is populated.
import src.collectors.rpi.dgft  # noqa: F401
import src.collectors.rpi.hmrc  # noqa: F401
import src.collectors.rpi.ukft  # noqa: F401
import src.collectors.rpi.uk_tra  # noqa: F401
import src.collectors.lsi.jnpt  # noqa: F401
import src.collectors.lsi.felixstowe  # noqa: F401
import src.collectors.lsi.carriers  # noqa: F401
import src.collectors.lsi.loadstar  # noqa: F401
import src.collectors.cpi.fx_inr_gbp  # noqa: F401
import src.collectors.cpi.cotton  # noqa: F401
import src.collectors.cpi.freight_rates  # noqa: F401
import src.collectors.cpi.forwarder_posts  # noqa: F401

from src.collectors.registry import get_collector, list_collectors
from src.collectors.source_config import SourceOverride, load_source_overrides
from src.config import settings
from src.db.models import PipelineRun, TradeLane
from src.db.session import async_session
from sqlalchemy import select

st.title("Source Admin")
st.caption("Current source configuration resolved from Google Sheets CSV and collector defaults.")


async def _load_overrides() -> dict[str, SourceOverride]:
    if not settings.sources_sheet_csv_url:
        return {}
    return await load_source_overrides(settings.sources_sheet_csv_url)


async def _load_recent_runs(limit: int = 25) -> list[PipelineRun]:
    async with async_session() as session:
        result = await session.execute(
            select(PipelineRun)
            .join(TradeLane, PipelineRun.trade_lane_id == TradeLane.id, isouter=True)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


sheet_location = settings.sources_sheet_csv_url
if sheet_location:
    st.code(f"SOURCES_SHEET_CSV_URL={sheet_location}")
else:
    st.warning("SOURCES_SHEET_CSV_URL is not set. Showing collector defaults only.")

try:
    overrides = asyncio.run(_load_overrides())
except Exception as exc:
    st.error(f"Could not load source config: {exc}")
    overrides = {}

collectors = list_collectors()
rows = []
for name in collectors:
    cls = get_collector(name)
    collector = cls()
    override = overrides.get(name)

    effective_name = override.source_name if override and override.source_name else collector.source_name
    effective_source_url = override.source_url if override and override.source_url else collector.source_url
    effective_scrape_url = (
        override.scrape_url
        if override and override.scrape_url
        else (override.source_url if override and override.source_url else collector.get_scrape_url())
    )
    effective_frequency = (
        override.check_frequency if override and override.check_frequency else collector.check_frequency
    )
    enabled = True if override is None else override.enabled

    rows.append(
        {
            "collector": name,
            "enabled": enabled,
            "source_name": effective_name,
            "source_url": effective_source_url,
            "scrape_url": effective_scrape_url,
            "check_frequency": effective_frequency,
            "index": collector.primary_index.value,
            "source_layer": collector.source_layer.value,
        }
    )

frame = pd.DataFrame(rows)

c1, c2, c3 = st.columns(3)
c1.metric("Collectors", len(frame))
c2.metric("Enabled", int(frame["enabled"].sum()) if not frame.empty else 0)
c3.metric("Disabled", int((~frame["enabled"]).sum()) if not frame.empty else 0)

st.subheader("Effective Runtime Config")
st.dataframe(frame.sort_values(["enabled", "collector"], ascending=[False, True]), use_container_width=True)

csv = frame.to_csv(index=False)
st.download_button(
    "Download effective config CSV",
    csv,
    "advuman_effective_source_config.csv",
    "text/csv",
)

st.divider()
st.subheader("Recent Automation Runs")

try:
    runs = asyncio.run(_load_recent_runs(limit=25))
except Exception as exc:
    st.error(f"Could not load run history: {exc}")
    runs = []

if runs:
    run_rows = []
    for run in runs:
        run_rows.append(
            {
                "id": run.id,
                "lane_id": run.trade_lane_id,
                "trigger": run.trigger,
                "stage": run.stage,
                "status": run.status.value,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "error_summary": run.error_summary or "",
            }
        )
    st.dataframe(pd.DataFrame(run_rows), use_container_width=True)
else:
    st.info("No automation runs recorded yet.")
