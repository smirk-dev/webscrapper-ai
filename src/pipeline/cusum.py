"""CUSUM (Cumulative Sum) detection for persistent shifts.

Source: Montgomery Ch. 9 + Ergashev comparison.
Used primarily for RPI (volatile signals with persistent small shifts).

Upper CUSUM: C⁺_t = max(0, C⁺_{t-1} + z_t - k)
Lower CUSUM: C⁻_t = min(0, C⁻_{t-1} + z_t + k)

Alert when C⁺ > h or |C⁻| > h.
"""

from dataclasses import dataclass


@dataclass
class CUSUMState:
    upper: float = 0.0
    lower: float = 0.0


class CUSUMDetector:
    """Track CUSUM statistics for a single index."""

    def __init__(self, k: float = 0.5, h: float = 4.5):
        self.k = k  # Reference value (sensitivity to 1-sigma shifts)
        self.h = h  # Control limit (alarm threshold)
        self.state = CUSUMState()

    def update(self, z_score: float) -> tuple[CUSUMState, bool]:
        """Update CUSUM with new z-score observation.

        Returns:
            (state, alarm) — current CUSUM state and whether threshold is breached.
        """
        self.state.upper = max(0.0, self.state.upper + z_score - self.k)
        self.state.lower = min(0.0, self.state.lower + z_score + self.k)

        alarm = self.state.upper > self.h or abs(self.state.lower) > self.h
        return self.state, alarm

    def reset(self) -> None:
        """Reset CUSUM after alarm or manual intervention."""
        self.state = CUSUMState()
