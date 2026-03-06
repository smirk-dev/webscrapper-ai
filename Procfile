# Procfile — used by Railway (and Heroku-compatible platforms).
#
# Railway: connect this repo; it auto-detects the Procfile.
# Add DATABASE_URL, ANTHROPIC_API_KEY, SOURCES_SHEET_CSV_URL as Railway variables.
#
# $PORT is injected by Railway automatically for the web process.

web: streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
worker: python scripts/schedule_sync_scrape.py --lane UK-India --daily-at 06:00
