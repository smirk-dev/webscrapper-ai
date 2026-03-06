# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Advuman** is an early-warning intelligence service for SMEs in volatile trade lanes. It monitors OSINT sources to detect deviations from baseline conditions across three composite indices (RPI, LSI, CPI), computes lane health status, and presents findings via a Streamlit dashboard.

## Architecture

```text
OSINT Collectors (12 sources) → PostgreSQL → Quant Pipeline → Streamlit Dashboard
```

- **Collectors** (`src/collectors/`): Scrape 12 OSINT sources per trade lane using httpx/BeautifulSoup/Playwright, then classify raw events into the 18-column schema via Claude API (LLM-assisted) or keyword-heuristic fallback.
- **Pipeline** (`src/pipeline/`): Weighted scoring → EWMA rolling baseline → z-score standardization → CUSUM detection → weekly roll-up → attribution decomposition.
- **Dashboard** (`src/dashboard/`): Streamlit app with 5 pages: Lane Overview, Signal Log, Index Charts, Source Admin, plus the main app entry.
- **Database**: PostgreSQL (cloud) via SQLAlchemy async. 7 tables: `trade_lanes`, `osint_sources`, `events`, `weighted_scores`, `index_snapshots`, `lane_health`, `pipeline_runs`.

## Three Composite Indices

- **RPI** (Regulatory Pressure Index): Regulation, enforcement, customs, trade remedies. CUSUM detection.
- **LSI** (Logistics Stress Index): Port congestion, shipping schedules, carrier disruptions. EWMA detection.
- **CPI** (Cost Pressure Index): FX volatility, input prices, tariffs, freight rates. EWMA detection.

## Lane Health: STABLE (0-3) / WATCH (4-7) / ACTIVE (8+)

Combined = sum of weekly RPI + LSI + CPI deltas.

## Weight Matrix

```text
WeightedScore = Delta × SourceWeight × StatusWeight × ConfidenceWeight × PrecedentWeight
Source:     Primary=1.0, Logistics=0.8, Market=0.7, Industry=0.6
Status:     Enforced=1.0, Announced=0.7, Draft=0.4
Confidence: High=1.0, Medium=0.7, Low=0.4
Precedent:  Novel=1.2, Known=1.0
```

## Environment Setup

```bash
# 1. Create .env file with:
ANTHROPIC_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/advuman
# Optional: dynamic source config from Google Sheets
SOURCES_SHEET_CSV_URL=https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=0

# 2. Install with dev dependencies
pip install -e ".[dev]"

# 3. Install Playwright browsers (for Felixstowe and Loadstar collectors)
playwright install
```

**Python**: Use 3.11+ (3.13+ recommended). On Windows, use the official Python installer — the Microsoft Store `python` alias resolves to the wrong install. The correct path is `/c/Users/surya/AppData/Local/Programs/Python/Python314/python.exe`.

## Commands

```bash
# Database
python scripts/bootstrap_db.py            # Create tables (cloud DB)
python scripts/bootstrap_db.py --local    # Create tables (local SQLite for offline dev)
python scripts/check_db_connection.py     # Diagnose cloud DB connectivity

# Collectors
python scripts/run_collectors.py --list                          # List all 12 collectors
python scripts/run_collectors.py --all --persist --no-llm        # Run all, persist, skip LLM
python scripts/run_collectors.py --source hmrc felixstowe --persist  # Run specific collectors
python scripts/run_collectors.py --all --persist --no-llm --local   # Offline mode (SQLite)

# Pipeline
python scripts/run_pipeline.py --lane UK-India           # Run index computation
python scripts/run_pipeline.py --local --lane UK-India   # Run against local SQLite

# Scheduling (auto sync from Google Sheets + scrape + pipeline)
python scripts/schedule_sync_scrape.py --lane UK-India --minutes 60 --no-llm
python scripts/schedule_sync_scrape.py --lane UK-India --daily-at 09:00 --no-llm

# Source config validation
python scripts/validate_source_sheet.py
python scripts/validate_source_sheet.py --strict

# Dashboard
streamlit run src/dashboard/app.py
# For local SQLite: set DATABASE_URL=sqlite+aiosqlite:///./advuman_local.db first

# Tests
pytest tests/                     # Run all tests
pytest tests/test_pipeline/       # Run pipeline tests only
pytest tests/test_pipeline/test_scoring.py::test_weight_matrix  # Run specific test
pytest tests/ -v --tb=short       # Verbose with short tracebacks
pytest tests/ --cov=src           # With coverage
```

## Collector Implementation Pattern

All collectors extend `BaseCollector` (`src/collectors/base.py`) and follow this flow:

1. **Scrape** → `RawEvent` (title, content, url, published_date)
2. **Classify** → `ClassifiedEvent` via Claude API (18-column schema, all enum-validated) or keyword-heuristic fallback when `--no-llm`
3. **Persist** → Store `events` + `weighted_scores` in database

**Registration**: Use `@register("name")` decorator. New collectors must be **imported** in `scripts/run_collectors.py` (lines 20-31) to auto-register.

**Collector Families** (all async):

- **RPI** (4): DGFT, HMRC, UKFT, UK-TRA — regulation, enforcement, customs, remedies
- **LSI** (4): Felixstowe, JNPT, Carriers, Loadstar — ports, schedules, disruptions
- **CPI** (4): FX INR/GBP, Cotton, Freight Rates, Forwarder Posts — costs, FX, tariffs

**Known Issues**:

- Felixstowe & Loadstar return 403 even with User-Agent spoofing → require Playwright
- HMRC may return 0 results depending on search terms
- Cotton (ICAC) & Freight Rates (FBX) require LLM text extraction from page (no structured data)

## Dynamic Source Management

Collector sources can be managed via a Google Sheet (published as CSV) so R&D/Marketing can update links without code changes. Set `SOURCES_SHEET_CSV_URL` in `.env`. The source config module (`src/collectors/source_config.py`) parses columns: `collector`, `enabled`, `source_name`, `source_url`, `scrape_url`, `check_frequency`. Template: `docs/source_config_template.csv`.

- `--all` runs only collectors where `enabled=true` (or blank)
- `--source ...` runs requested collectors even if disabled in sheet

## Key Patterns

**Async throughout**: All collectors, database queries, and pipeline steps use async. `asyncpg` + SQLAlchemy async in production; tests use synchronous in-memory SQLite via `conftest.py`.

**Config**: `src/config.py` uses pydantic-settings `BaseSettings` loading from `.env`. The `database_url` validator auto-normalizes `postgres://` and `postgresql://` to `postgresql+asyncpg://`.

**Test database**: All tests use in-memory SQLite with synchronous sessions. `pytest-asyncio` with `asyncio_mode="auto"` in `pyproject.toml`.

**Pipeline run logging**: Scheduled/manual runs are tracked in `pipeline_runs` table and visible on the Source Admin dashboard page.

## Trade Lanes

Currently implemented: **UK-India Textiles** (12 sources). Designed to expand to UK-Vietnam and UK-Egypt. Each lane uses the same 18-column event schema and identical index math.

## Docs

- `docs/` contains 18 PDFs with business plans, SOPs, OSINT source guides, sprint plans, and the 36-source annotated bibliography for the index math framework. Treat as requirements reference.
- `docs/deployment_supabase_streamlit.md` — production deployment runbook for Supabase + Streamlit Cloud.
