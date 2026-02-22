"""Test EWMA rolling baseline."""

import pytest

from src.pipeline.ewma import EWMABaseline, lambda_from_halflife


def test_lambda_from_halflife_14_days():
    lam = lambda_from_halflife(14)
    assert lam == pytest.approx(0.04831, abs=0.001)


def test_ewma_first_observation():
    ewma = EWMABaseline(lam=0.1)
    mean, sigma = ewma.update(5.0)
    assert mean == 5.0
    assert sigma == 0.0


def test_ewma_converges_toward_new_value():
    ewma = EWMABaseline(lam=0.1)
    ewma.update(0.0)  # Initialize at 0

    # Feed constant value of 10 repeatedly
    for _ in range(100):
        mean, sigma = ewma.update(10.0)

    # Should converge close to 10
    assert mean == pytest.approx(10.0, abs=0.1)


def test_ewma_sigma_increases_with_volatility():
    ewma = EWMABaseline(lam=0.1)
    ewma.update(5.0)

    # Alternating values should increase sigma
    for i in range(20):
        val = 10.0 if i % 2 == 0 else 0.0
        _, sigma = ewma.update(val)

    assert sigma > 0
