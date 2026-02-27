# Advuman

Early-warning trade intelligence for SMEs in volatile lanes.

Advuman monitors OSINT sources, classifies events into a structured schema, computes composite risk indices (RPI/LSI/CPI), and surfaces weekly lane health in a Streamlit dashboard.

## Current Scope

- Lane: **UK-India (Textiles)**
- Sources: **12 collectors** (RPI: 4, LSI: 4, CPI: 4)
- Pipeline: weighted scoring, EWMA baseline, z-score, CUSUM, weekly roll-up, attribution
- UI: Streamlit pages for lane overview, signal log, and index charts

## Architecture

```text
Collectors (OSINT) -> Event Classification -> PostgreSQL -> Quant Pipeline -> Streamlit Dashboard
```

## Quick Start

### 1) Environment

- Python: **3.11+** (3.13+ recommended)
- Create `.env` from `.env.example`

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/advuman
ANTHROPIC_API_KEY=sk-...
```

### 2) Install

```bash
pip install -e ".[dev]"
playwright install
```

### 3) Database

```bash
python scripts/bootstrap_db.py
```

For offline/local development when cloud Postgres is unavailable:

```bash
python scripts/bootstrap_db.py --local
```

### Troubleshooting (Windows + Python 3.14)

If `alembic upgrade head` hangs or errors while importing SQLAlchemy, use:

```powershell
python scripts/bootstrap_db.py
```

`bootstrap_db.py` sets `DISABLE_SQLALCHEMY_CEXT_RUNTIME=1` automatically on Windows with Python 3.14+.

If bootstrap fails with timeout/network errors (e.g. `WinError 121`), run:

```powershell
python scripts/check_db_connection.py
```

This checks DNS, TCP reachability, and asyncpg login using your current `DATABASE_URL`.

If cloud DB connectivity still fails, continue locally with:

```powershell
python scripts/bootstrap_db.py --local
```

### 4) Run

```bash
python scripts/run_collectors.py --list
python scripts/run_collectors.py --all
python scripts/run_pipeline.py --lane UK-India
streamlit run src/dashboard/app.py
```

Local/offline run path:

```powershell
python scripts/bootstrap_db.py --local
python scripts/run_collectors.py --all --persist --no-llm --local
python scripts/run_pipeline.py --local --lane UK-India
$env:DATABASE_URL = "sqlite+aiosqlite:///./advuman_local.db"
streamlit run src/dashboard/app.py
```

### 5) Test

```bash
pytest tests/
```

## Functional Status (latest local run)

- Pipeline tests: **18 passed** (`tests/test_pipeline`)
- Collector registry smoke test: **12 collectors listed** (`run_collectors.py --list`)

## Production Deployment (Supabase + Streamlit Cloud)

Use the full deployment runbook here:

- `docs/deployment_supabase_streamlit.md`

## Working Roadmap

Use this as your execution plan and tick items as you complete them.

### Phase 1 — Stabilize Core (1-2 weeks)

- [ ] Add Alembic migration revision(s) for all current ORM models
- [ ] Add CI workflow (lint + tests on PR)
- [ ] Add collector-level unit tests (parsing fixtures for each source family)
- [ ] Add robust retry/backoff + timeout policy for HTTP/Playwright collectors
- [ ] Add structured logging for collectors/pipeline runs

### Phase 1 Exit Criteria

- [ ] CI green on every PR
- [ ] Database can be recreated from migrations only
- [ ] Collectors fail gracefully without crashing batch run

### Phase 2 — Data Quality & Classification (1-2 weeks)

- [ ] Add schema-level validation tests for the 18-column `ClassifiedEvent`
- [ ] Add prompt/version tracking for classifier outputs
- [ ] Add relevance and enum coercion fallback handling in classifier
- [ ] Add duplicate-event detection (URL + date + title hash)
- [ ] Add reviewed/override workflow for analyst corrections

### Phase 2 Exit Criteria

- [ ] Invalid classifier responses do not break ingestion
- [ ] Duplicate events are suppressed or linked
- [ ] Manual review path exists for low-confidence signals

### Phase 3 — Pipeline Hardening (1 week)

- [ ] Persist daily `IndexSnapshot` and weekly `LaneHealth` from runner
- [ ] Add end-to-end test from sample events to lane health
- [ ] Add attribution consistency checks (percent sums and pathway splits)
- [ ] Parameterize EWMA/CUSUM per lane/index in config

### Phase 3 Exit Criteria

- [ ] Weekly run produces reproducible metrics
- [ ] Dashboard always has a complete snapshot series to render

### Phase 4 — Dashboard MVP+ (1 week)

- [ ] Add lane selector (prepare for UK-Vietnam / UK-Egypt)
- [ ] Add event detail drilldown page with source links
- [ ] Add health trend summary cards (1w/4w delta)
- [ ] Add CSV export for lane health + snapshots

### Phase 4 Exit Criteria

- [ ] Non-technical user can read current status and top drivers in <2 mins
- [ ] Dashboard supports at least 2 lanes without code changes

### Phase 5 — Ops & Automation (1 week)

- [ ] Add scheduled runs (collectors + pipeline)
- [ ] Add run metadata table (`started_at`, `finished_at`, `status`, `errors`)
- [ ] Add alerting hooks for WATCH/ACTIVE transitions
- [ ] Add basic runbook docs for incident handling

### Phase 5 Exit Criteria

- [ ] Daily automation runs unattended
- [ ] Failures are visible with actionable logs
- [ ] Health state changes can trigger notifications

## Suggested Branching Strategy Going Forward

- Keep stacked feature branches for large multi-part work.
- Open one PR per feature area (DB, collectors, pipeline, dashboard, config).
- Use PR templates with:
  - scope summary,
  - validation commands run,
  - screenshots (dashboard changes),
  - rollout notes.

## Project Layout

```text
scripts/         # CLI runners (collectors, pipeline, seed)
src/collectors/  # OSINT collectors + classifier + registry
src/db/          # SQLAlchemy models, session, seed logic
src/pipeline/    # scoring, ewma, zscore, cusum, rollup, attribution
src/dashboard/   # Streamlit app + pages
tests/           # pipeline and collector test coverage
```
