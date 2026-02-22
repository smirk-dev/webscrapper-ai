"""EWMA (Exponentially Weighted Moving Average) rolling baseline.

Source: RiskMetrics + Stanford EWMM paper (Boyd 2024).
Formula:
    μ_t = λ × x_t + (1 - λ) × μ_{t-1}
    σ²_t = λ × (x_t - μ_t)² + (1 - λ) × σ²_{t-1}

Half-life relationship: λ = 1 - 2^(-1/H)
Default H=14 days → λ ≈ 0.048
"""

import math


def lambda_from_halflife(half_life_days: float) -> float:
    """Convert half-life in days to EWMA decay parameter lambda."""
    return 1 - 2 ** (-1 / half_life_days)


class EWMABaseline:
    """Track EWMA mean and variance for a single index time series."""

    def __init__(self, lam: float = 0.048):
        self.lam = lam
        self.mean: float | None = None
        self.variance: float | None = None

    def update(self, x: float) -> tuple[float, float]:
        """Update with new observation, return (mean, sigma).

        For the first observation, initializes mean=x and variance=0.
        """
        if self.mean is None:
            self.mean = x
            self.variance = 0.0
            return self.mean, 0.0

        self.mean = self.lam * x + (1 - self.lam) * self.mean
        self.variance = self.lam * (x - self.mean) ** 2 + (1 - self.lam) * self.variance
        sigma = math.sqrt(self.variance) if self.variance > 0 else 0.0
        return self.mean, sigma
