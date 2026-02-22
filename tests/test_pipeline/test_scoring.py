"""Test the weighted scoring logic against Danha's sprint plan examples."""

from src.db.seed import (
    CONFIDENCE_WEIGHTS,
    PRECEDENT_WEIGHTS,
    SOURCE_WEIGHTS,
    STATUS_WEIGHTS,
)
from src.db.models import SourceLayer


def compute_weighted_score(
    delta: int,
    source_layer: SourceLayer,
    event_status: str,
    confidence: str,
    historical_precedent: bool,
) -> float:
    """Replicate the weight matrix formula from Danha's sprint plan."""
    return (
        delta
        * SOURCE_WEIGHTS[source_layer]
        * STATUS_WEIGHTS[event_status]
        * CONFIDENCE_WEIGHTS[confidence]
        * PRECEDENT_WEIGHTS[historical_precedent]
    )


def test_dgft_interest_subvention():
    """From Danha's sprint plan: DGFT Interest Subvention = -1 × 1.0 × 0.4 × 1.0 × 1.0 = -0.4"""
    score = compute_weighted_score(
        delta=-1,
        source_layer=SourceLayer.PRIMARY,
        event_status="Draft",
        confidence="High",
        historical_precedent=True,
    )
    assert score == pytest.approx(-0.4)


def test_felixstowe_storm():
    """From Danha's sprint plan: Felixstowe Storm = +1 × 0.8 × 1.0 × 1.0 × 1.0 = +0.8"""
    score = compute_weighted_score(
        delta=+1,
        source_layer=SourceLayer.LOGISTICS,
        event_status="Enforced",
        confidence="High",
        historical_precedent=True,
    )
    assert score == pytest.approx(0.8)


def test_novel_event_gets_higher_weight():
    """Novel events (no precedent) get 1.2× multiplier."""
    novel = compute_weighted_score(
        delta=+1,
        source_layer=SourceLayer.PRIMARY,
        event_status="Announced",
        confidence="High",
        historical_precedent=False,
    )
    known = compute_weighted_score(
        delta=+1,
        source_layer=SourceLayer.PRIMARY,
        event_status="Announced",
        confidence="High",
        historical_precedent=True,
    )
    assert novel > known
    assert novel / known == pytest.approx(1.2)


def test_low_confidence_industry_draft():
    """Low confidence + Industry + Draft = minimal weight."""
    score = compute_weighted_score(
        delta=+1,
        source_layer=SourceLayer.INDUSTRY,
        event_status="Draft",
        confidence="Low",
        historical_precedent=True,
    )
    # 1 × 0.6 × 0.4 × 0.4 × 1.0 = 0.096
    assert score == pytest.approx(0.096)


import pytest
