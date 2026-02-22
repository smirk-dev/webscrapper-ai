"""Test weekly roll-up and Lane Health calculation.

Uses the simulated pilot data from docs/document_pdf (9).pdf:
Week of Jan 19-23, 2026: RPI=5, LSI=2, CPI=2, Combined=9 → ACTIVE
"""

from src.db.models import HealthStatus
from src.pipeline.rollup import compute_lane_health


def test_pilot_week_is_active():
    """From simulated pilot data: RPI=5, LSI=2, CPI=2 → Combined=9 → ACTIVE"""
    combined, health = compute_lane_health(5, 2, 2)
    assert combined == 9
    assert health == HealthStatus.ACTIVE


def test_stable_lane():
    combined, health = compute_lane_health(1, 1, 0)
    assert combined == 2
    assert health == HealthStatus.STABLE


def test_watch_lane():
    combined, health = compute_lane_health(2, 1, 2)
    assert combined == 5
    assert health == HealthStatus.WATCH


def test_zero_signals():
    combined, health = compute_lane_health(0, 0, 0)
    assert combined == 0
    assert health == HealthStatus.STABLE


def test_boundary_watch():
    """Exactly 4 → WATCH"""
    combined, health = compute_lane_health(2, 1, 1)
    assert combined == 4
    assert health == HealthStatus.WATCH


def test_boundary_active():
    """Exactly 8 → ACTIVE"""
    combined, health = compute_lane_health(3, 3, 2)
    assert combined == 8
    assert health == HealthStatus.ACTIVE
