"""Populate the database with reference data."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.seed import main

if __name__ == "__main__":
    asyncio.run(main())
