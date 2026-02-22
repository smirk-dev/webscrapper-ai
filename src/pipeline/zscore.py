"""Z-score standardization using EWMA baseline.

Formula: z_t = (x_t - μ_t) / σ_t

Source: GSCPI (NY Fed) methodology — express deviation in sigma units.
"""


def compute_zscore(value: float, ewma_mean: float, ewma_sigma: float) -> float | None:
    """Compute z-score relative to EWMA baseline.

    Returns None if sigma is zero (insufficient data for deviation).
    """
    if ewma_sigma <= 0:
        return None
    return (value - ewma_mean) / ewma_sigma
