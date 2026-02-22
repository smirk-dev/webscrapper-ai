"""Weighted signal scoring using Danha's weight matrix.

Formula: WeightedScore = Delta × SourceWeight × StatusWeight × ConfidenceWeight × PrecedentWeight
"""

from src.db.models import ConfidenceLevel, EventStatus, SourceLayer
from src.db.seed import CONFIDENCE_WEIGHTS, PRECEDENT_WEIGHTS, SOURCE_WEIGHTS, STATUS_WEIGHTS


def compute_weighted_score(
    delta: int,
    source_layer: SourceLayer,
    event_status: EventStatus,
    confidence_level: ConfidenceLevel,
    historical_precedent: bool,
) -> tuple[float, float, float, float, float]:
    """Compute the weighted score and return all component weights.

    Returns:
        (weighted_score, source_w, status_w, confidence_w, precedent_w)
    """
    source_w = SOURCE_WEIGHTS[source_layer]
    status_w = STATUS_WEIGHTS[event_status.value]
    confidence_w = CONFIDENCE_WEIGHTS[confidence_level.value]
    precedent_w = PRECEDENT_WEIGHTS[historical_precedent]

    weighted_score = delta * source_w * status_w * confidence_w * precedent_w

    return weighted_score, source_w, status_w, confidence_w, precedent_w
