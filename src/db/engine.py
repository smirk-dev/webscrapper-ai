from sqlalchemy import pool


def get_async_engine_options(database_url: str) -> dict:
    options: dict = {"echo": False}

    if database_url.startswith("postgresql+asyncpg") and "pooler.supabase.com" in database_url:
        options["poolclass"] = pool.NullPool
        options["connect_args"] = {"statement_cache_size": 0}

    return options
