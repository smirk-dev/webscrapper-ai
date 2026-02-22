# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Advuman** is an early-warning intelligence service for SMEs in volatile trade lanes. It monitors OSINT sources to detect deviations from baseline conditions across three composite indices (RPI, LSI, CPI), computes lane health status, and presents findings via a Streamlit dashboard.

## Architecture

```text
OSINT Collectors (12 sources) → PostgreSQL → Quant Pipeline → Streamlit Dashboard
```

- **Collectors** (`src/collectors/`): Scrape 12 OSINT sources per trade lane using httpx/BeautifulSoup/Playwright, then classify raw events into the 18-column schema via Claude API (LLM-assisted).
- **Pipeline** (`src/pipeline/`): Weighted scoring → EWMA rolling baseline → z-score standardization → CUSUM detection → weekly roll-up → attribution decomposition.
- **Dashboard** (`src/dashboard/`): Streamlit app with 3 pages: Lane Overview, Signal Log, Index Charts.
- **Database**: PostgreSQL (cloud) via SQLAlchemy async. 6 tables: `trade_lanes`, `osint_sources`, `events`, `weighted_scores`, `index_snapshots`, `lane_health`.

## Three Composite Indices

- **RPI** (Regulatory Pressure Index): Regulation, enforcement, customs, trade remedies. CUSUM detection.
- **LSI** (Logistics Stress Index): Port congestion, shipping schedules, carrier disruptions. EWMA detection.
- **CPI** (Cost Pressure Index): FX volatility, input prices, tariffs, freight rates. EWMA detection.

## Lane Health: STABLE (0-3) / WATCH (4-7) / ACTIVE (8+)

Combined = sum of weekly RPI + LSI + CPI deltas.

## Weight Matrix (Danha's sprint plan)

```text
WeightedScore = Delta × SourceWeight × StatusWeight × ConfidenceWeight × PrecedentWeight
Source:     Primary=1.0, Logistics=0.8, Market=0.7, Industry=0.6
Status:     Enforced=1.0, Announced=0.7, Draft=0.4
Confidence: High=1.0, Medium=0.7, Low=0.4
Precedent:  Novel=1.2, Known=1.0
```

## Environment Setup

Before developing, configure:

```bash
# 1. Create .env file with:
ANTHROPIC_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/advuman

# 2. Install Playwright browsers (for Felixstowe and Loadstar collectors):
playwright install
```

**Important**: Use Python 3.11+ (3.13+ recommended). On Windows, use the official Python installer, not the Microsoft Store version.

## Commands

```bash
pip install -e ".[dev]"           # Install with dev dependencies

# Database
alembic upgrade head              # Run migrations
python scripts/seed_db.py         # Seed UK-India OSINT sources

# Collectors (12 sources across RPI/LSI/CPI)
python scripts/run_collectors.py --list          # List all 12 collectors
python scripts/run_collectors.py --all           # Run all collectors
python scripts/run_collectors.py --source hmrc felixstowe  # Run specific collectors

# Pipeline (quant scoring, anomaly detection, weekly rollup)
python scripts/run_pipeline.py --lane UK-India   # Run index computation

# Dashboard
streamlit run src/dashboard/app.py               # Launch Streamlit app (3 pages)

# Tests
pytest tests/                     # Run all tests
pytest tests/test_pipeline/       # Run pipeline tests only
pytest tests/test_pipeline/test_scoring.py::test_weight_matrix  # Run specific test
pytest tests/ -v --tb=short       # Verbose output with short tracebacks
pytest tests/ --cov=src           # Run with coverage report
```

## Collector Implementation Pattern

All collectors extend `BaseCollector` (in `src/collectors/base.py`) and follow this flow:

1. **Scrape** → `RawEvent` (title, content, url, published_date)
2. **Classify** → `ClassifiedEvent` via Claude API (18-column schema, all enum-validated)
3. **Persist** → Store `weighted_scores` in PostgreSQL

**Key**: Register collectors with `@register("name")` decorator. Collectors must be **imported** in `scripts/run_collectors.py` to auto-register (see line 18-29).

**18-Column ClassifiedEvent Schema**:

- Metadata: date_observed, source_layer, source_name, source_url
- Classification: event_type, jurisdiction, sector, affected_object, event_description
- Assessment: event_status, confidence_level, historical_precedent, impact_pathway, quant_metric_triggered
- Quantization: index_impact (RPI/LSI/CPI), index_delta (+1/0/-1), analyst_notes

**Collector Families** (all async):

- **RPI** (4): DGFT, HMRC, UKFT, UK-TRA — regulation, enforcement, customs, remedies
- **LSI** (4): Felixstowe, JNPT, Carriers, Loadstar — ports, schedules, disruptions
- **CPI** (4): FX INR/GBP, Cotton, Freight Rates, Forwarder Posts — costs, FX, tariffs

**Known Issues**:

- Felixstowe & Loadstar return 403 even with User-Agent spoofing → require Playwright
- HMRC may return 0 results depending on search terms
- Cotton (ICAC) & Freight Rates (FBX) require LLM text extraction from page (no structured data)

## Key Files

- `src/config.py` — Settings (DB URL, API keys, EWMA lambda, CUSUM params)
- `src/db/models.py` — SQLAlchemy ORM models (6 tables, all enums)
- `src/db/seed.py` — 12 UK-India OSINT sources + weight matrix constants
- `src/db/session.py` — AsyncSession factory for async SQLAlchemy
- `src/collectors/base.py` — BaseCollector ABC + RawEvent/ClassifiedEvent dataclasses
- `src/collectors/registry.py` — @register decorator and collector discovery
- `src/collectors/classifier.py` — LLM classification prompt + Claude API integration
- `src/pipeline/scoring.py` — Weighted signal scoring
- `src/pipeline/ewma.py` — EWMA rolling baseline (λ=0.048, 14-day half-life)
- `src/pipeline/zscore.py` — Z-score standardization across indices
- `src/pipeline/cusum.py` — CUSUM persistent shift detection (k=0.5, h=4.5)
- `src/pipeline/rollup.py` — Weekly lane health computation
- `src/pipeline/attribution.py` — Contribution decomposition by source/pathway/jurisdiction

## Data Flow & Key Patterns

**Async throughout**: All collectors, database queries, and pipeline steps are async. Use `asyncpg` + `SQLAlchemy` async and `await` everywhere. Test fixtures use synchronous in-memory SQLite via `conftest.py`.

**Weekly pipeline cycle**:

1. Collectors scrape 12 OSINT sources → `RawEvent` dataclass
2. Classifier (Claude API) validates/enriches → `ClassifiedEvent` (18 columns)
3. Scoring applies weight matrix (`src/config.py`) → stores `weighted_scores`
4. EWMA computes baseline per index (rolling 14-day window, λ=0.048)
5. Z-score standardization across all sources
6. CUSUM detects persistent shifts (k=0.5, h=4.5 → alarm on 4.5-sigma)
7. Weekly rollup sums deltas → lane health status (STABLE/WATCH/ACTIVE)
8. Dashboard queries snapshots and displays via Streamlit

**Test database**: All tests use in-memory SQLite. Async tests via `pytest-asyncio` (asyncio_mode="auto" in `pyproject.toml`).

## Trade Lanes

Currently implemented: **UK-India Textiles** (12 sources). Designed to expand to UK-Vietnam and UK-Egypt. Each lane uses the same 18-column event schema and identical index math.

## Docs

`docs/` contains 18 PDFs with business plans, SOPs, OSINT source guides, sprint plans, and the 36-source annotated bibliography for the index math framework. These are the original design documents — treat as requirements reference.
