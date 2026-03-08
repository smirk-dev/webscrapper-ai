"""Validate dynamic source configuration from Google Sheets CSV or local CSV.

Usage:
    python scripts/validate_source_sheet.py
    python scripts/validate_source_sheet.py --csv docs/source_config_template.csv
    python scripts/validate_source_sheet.py --strict
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

from src.collectors.registry import list_collectors
from src.collectors.source_config import load_source_overrides
from src.config import settings


async def validate(csv_location: str, strict: bool = False) -> int:
    available = set(list_collectors())

    if not csv_location:
        print(
            "ERROR: No CSV source configured. Set SOURCES_SHEET_CSV_URL or pass --csv."
        )
        return 2

    try:
        overrides = await load_source_overrides(csv_location)
    except Exception as exc:
        print(f"ERROR: Could not load source config: {exc}")
        return 2

    if not overrides:
        print("WARNING: Config loaded but no collector rows were found.")
        return 1 if strict else 0

    row_collectors = set(overrides.keys())
    unknown = sorted(row_collectors - available)
    missing = sorted(available - row_collectors)

    invalid_frequency = sorted(
        name
        for name, row in overrides.items()
        if row.check_frequency is None and row.collector in available
    )

    print(f"Loaded {len(overrides)} row(s) from: {csv_location}")
    print(f"Registered collectors: {len(available)}")

    if unknown:
        print("\nUnknown collectors in CSV:")
        for name in unknown:
            print(f"  - {name}")

    if missing:
        print("\nCollectors missing from CSV:")
        for name in missing:
            print(f"  - {name}")

    if invalid_frequency:
        print(
            "\nRows with blank/invalid check_frequency (will keep collector default):"
        )
        for name in invalid_frequency:
            print(f"  - {name}")

    enabled = [
        name for name, row in overrides.items() if row.enabled and name in available
    ]
    disabled = [
        name for name, row in overrides.items() if not row.enabled and name in available
    ]
    print(f"\nEnabled: {len(enabled)} | Disabled: {len(disabled)}")

    has_errors = bool(unknown)
    has_warnings = bool(missing or invalid_frequency)

    if has_errors:
        print("\nValidation result: FAILED")
        return 1
    if strict and has_warnings:
        print("\nValidation result: FAILED (strict mode)")
        return 1

    print("\nValidation result: OK")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate dynamic source sheet configuration"
    )
    parser.add_argument("--csv", default="", help="CSV URL or local CSV path")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")
    args = parser.parse_args()

    csv_location = args.csv or settings.sources_sheet_csv_url
    exit_code = asyncio.run(validate(csv_location, strict=args.strict))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
