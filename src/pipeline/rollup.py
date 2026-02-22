"""Weekly roll-up and Lane Health calculation.

Lane Health Status Rules (from OSINT guides):
    Combined Total 0-3  → STABLE
    Combined Total 4-7  → WATCH
    Combined Total 8+   → ACTIVE
"""

from src.config import settings
from src.db.models import HealthStatus


def compute_lane_health(
    rpi_total: float,
    lsi_total: float,
    cpi_total: float,
) -> tuple[float, HealthStatus]:
    """Compute combined total and determine Lane Health status.

    Returns:
        (combined_total, health_status)
    """
    combined = rpi_total + lsi_total + cpi_total

    if combined >= settings.lane_health_active:
        status = HealthStatus.ACTIVE
    elif combined >= settings.lane_health_watch:
        status = HealthStatus.WATCH
    else:
        status = HealthStatus.STABLE

    return combined, status
