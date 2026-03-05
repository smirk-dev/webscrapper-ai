import pytest

from src.collectors.source_config import load_source_overrides, parse_source_overrides


def test_parse_source_overrides_normalizes_rows() -> None:
    rows = [
        {
            "collector": "hmrc",
            "enabled": "true",
            "source_name": "HMRC Live",
            "source_url": "https://example.org/hmrc",
            "scrape_url": "https://example.org/hmrc/search",
            "check_frequency": "weekly",
        },
        {
            "collector": "dgft",
            "enabled": "0",
            "source_url": "https://example.org/dgft",
            "check_frequency": "DAY",
        },
    ]

    overrides = parse_source_overrides(rows)

    assert overrides["hmrc"].enabled is True
    assert overrides["hmrc"].source_name == "HMRC Live"
    assert overrides["hmrc"].source_url == "https://example.org/hmrc"
    assert overrides["hmrc"].scrape_url == "https://example.org/hmrc/search"
    assert overrides["hmrc"].check_frequency == "weekly"

    assert overrides["dgft"].enabled is False
    assert overrides["dgft"].check_frequency == "daily"


@pytest.mark.asyncio
async def test_load_source_overrides_from_local_csv(tmp_path) -> None:
    csv_file = tmp_path / "sources.csv"
    csv_file.write_text(
        "collector,enabled,source_url,scrape_url,check_frequency\n"
        "loadstar,yes,https://example.org/loadstar,https://example.org/loadstar?s=india,daily\n",
        encoding="utf-8",
    )

    overrides = await load_source_overrides(str(csv_file))

    assert "loadstar" in overrides
    assert overrides["loadstar"].enabled is True
    assert overrides["loadstar"].source_url == "https://example.org/loadstar"
    assert overrides["loadstar"].scrape_url == "https://example.org/loadstar?s=india"
