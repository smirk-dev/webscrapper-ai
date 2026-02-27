"""Quick DB connectivity diagnostics for Advuman.

Checks:
1) DATABASE_URL presence and parsing
2) DNS resolution for DB host
3) TCP reachability to host:port
4) asyncpg connect attempt (short timeout)
"""

import asyncio
import socket
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from src.config import settings


def _masked_url(url: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.netloc
    if "@" in netloc:
        creds, hostpart = netloc.rsplit("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            creds = f"{user}:***"
        else:
            creds = "***"
        netloc = f"{creds}@{hostpart}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _asyncpg_url(url: str) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme.replace("+asyncpg", "")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("sslmode") == "require" and "ssl" not in query:
        query["ssl"] = "require"
    return urlunsplit((scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _extract_host_port(url: str) -> tuple[str | None, int]:
    parsed = urlsplit(url)
    host = parsed.hostname
    port = parsed.port or 5432
    return host, port


def _check_dns(host: str) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, None)
        resolved = sorted({info[4][0] for info in infos})
        return True, ", ".join(resolved[:4])
    except Exception as exc:
        return False, str(exc)


def _check_tcp(host: str, port: int, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"Connected to {host}:{port}"
    except Exception as exc:
        return False, str(exc)


async def _check_asyncpg(url: str) -> tuple[bool, str]:
    try:
        host = urlsplit(url).hostname or ""
        connect_kwargs = {"timeout": 10}
        if "pooler.supabase.com" in host:
            connect_kwargs["statement_cache_size"] = 0

        conn = await asyncpg.connect(url, **connect_kwargs)
        try:
            value = await conn.fetchval("select 1")
            return True, f"Query ok (select 1 => {value})"
        finally:
            await conn.close()
    except Exception as exc:
        text = str(exc).strip()
        return False, text if text else repr(exc)


def main() -> int:
    url = settings.database_url
    print("DATABASE_URL:", _masked_url(url))

    host, port = _extract_host_port(url)
    if not host:
        print("[FAIL] Could not parse host from DATABASE_URL")
        return 2

    print(f"Parsed host={host}, port={port}")

    ok_dns, dns_msg = _check_dns(host)
    print("[OK]" if ok_dns else "[FAIL]", "DNS:", dns_msg)

    ok_tcp, tcp_msg = _check_tcp(host, port)
    print("[OK]" if ok_tcp else "[FAIL]", "TCP:", tcp_msg)

    pg_url = _asyncpg_url(url)
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    ok_pg, pg_msg = asyncio.run(_check_asyncpg(pg_url))
    print("[OK]" if ok_pg else "[FAIL]", "asyncpg:", pg_msg)

    if ok_dns and ok_tcp and ok_pg:
        print("\nDatabase connectivity looks good.")
        return 0

    print("\nConnectivity check failed. Verify DATABASE_URL, firewall/VPN, host allowlist, and SSL requirements.")
    if "supabase.co" in host and "sslmode" not in query and "ssl" not in query:
        print("Hint: Supabase often requires SSL. Try adding '?sslmode=require' to DATABASE_URL.")
    if not ok_tcp and port == 5432 and "supabase.co" in host:
        print("Hint: If direct DB port is blocked on your network, use Supabase pooler connection string/port from dashboard.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())