# Deploy Advuman: Supabase + Streamlit Cloud

This guide deploys a publicly accessible dashboard backed by Supabase Postgres.

## 1) Create Supabase Postgres

1. Create a new Supabase project.
2. In **Project Settings → Database**, copy the **Connection string** for the pooler.
3. Use the SQLAlchemy async URL format in this project:

```text
postgresql+asyncpg://postgres.<PROJECT_REF>:<PASSWORD>@aws-0-<REGION>.pooler.supabase.com:6543/postgres?ssl=require
```

Notes:
- Keep `?ssl=require`.
- Prefer pooler port `6543` for app connections.

## 2) Initialize schema + seed data

From your machine (not Streamlit Cloud):

```bash
python scripts/bootstrap_db.py
python scripts/seed_db.py
```

If your `.env` has `DATABASE_URL` set to Supabase, bootstrap + seed will target Supabase.

## 3) Ingest data and compute weekly snapshots

```bash
python scripts/run_collectors.py --all --persist --lane UK-India
python scripts/run_pipeline.py --lane UK-India
```

Optional non-LLM fallback mode:

```bash
python scripts/run_collectors.py --all --persist --no-llm --lane UK-India
python scripts/run_pipeline.py --lane UK-India
```

## 4) Deploy on Streamlit Cloud

1. Push this repository to GitHub.
2. In Streamlit Cloud, create a new app.
3. Configure:
   - **Repository**: this repo
   - **Branch**: `main`
   - **Main file path**: `src/dashboard/app.py`
4. In **Advanced settings → Secrets**, add:

```toml
DATABASE_URL = "postgresql+asyncpg://postgres.<PROJECT_REF>:<PASSWORD>@aws-0-<REGION>.pooler.supabase.com:6543/postgres?ssl=require"
ANTHROPIC_API_KEY = "sk-ant-..."
```

You can copy values from `.streamlit/secrets.toml.example`.

`ANTHROPIC_API_KEY` is optional for dashboard-only usage, but needed for LLM-based classification jobs.

## 5) Make it accessible

- Set app visibility to **Public** in Streamlit Cloud sharing settings.
- Share the generated Streamlit app URL.

## 6) Keep data fresh

Streamlit Cloud only hosts the dashboard UI. Schedule collector/pipeline jobs externally:
- GitHub Actions scheduled workflow, or
- VM/cron job running:

```bash
python scripts/run_collectors.py --all --persist --lane UK-India
python scripts/run_pipeline.py --lane UK-India
```

## 7) Verify deployment

- Dashboard loads without `DATABASE_URL` errors.
- `Lane Overview` shows latest weekly health.
- `Signal Log` has event rows.
- `Index Charts` renders all 3 indices.
