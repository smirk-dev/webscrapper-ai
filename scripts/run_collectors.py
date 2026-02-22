"""CLI to run OSINT collectors.

Usage:
    python scripts/run_collectors.py --all
    python scripts/run_collectors.py --source hmrc
    python scripts/run_collectors.py --source hmrc felixstowe fx_inr_gbp
    python scripts/run_collectors.py --list
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import all collector modules so they register themselves
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


async def run_single(name: str) -> None:
    print(f"\n{'='*60}")
    print(f"Running collector: {name}")
    print(f"{'='*60}")

    collector_cls = get_collector(name)
    collector = collector_cls()

    try:
        events = await collector.collect()
        print(f"  Found {len(events)} raw event(s)")
        for i, event in enumerate(events, 1):
            print(f"  [{i}] {event.title}")
            if event.content:
                preview = event.content[:120].replace("\n", " ")
                print(f"      {preview}...")
    except Exception as e:
        print(f"  ERROR: {e}")


async def main(args: argparse.Namespace) -> None:
    if args.list:
        print("Available collectors:")
        for name in list_collectors():
            print(f"  - {name}")
        return

    if args.all:
        names = list_collectors()
    else:
        names = args.source

    if not names:
        print("No collectors specified. Use --all or --source <name>")
        return

    for name in names:
        await run_single(name)

    print(f"\nDone. Ran {len(names)} collector(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Advuman OSINT collectors")
    parser.add_argument("--all", action="store_true", help="Run all collectors")
    parser.add_argument("--source", nargs="+", default=[], help="Specific collector(s) to run")
    parser.add_argument("--list", action="store_true", help="List available collectors")
    args = parser.parse_args()
    asyncio.run(main(args))
