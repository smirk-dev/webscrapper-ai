"""Test CUSUM detection."""

from src.pipeline.cusum import CUSUMDetector


def test_cusum_no_alarm_at_zero():
    detector = CUSUMDetector(k=0.5, h=4.5)
    state, alarm = detector.update(0.0)
    assert not alarm
    assert state.upper == 0.0
    assert state.lower == 0.0


def test_cusum_accumulates_positive_shifts():
    detector = CUSUMDetector(k=0.5, h=4.5)
    # Feed persistent +1.5 sigma observations
    for _ in range(5):
        state, alarm = detector.update(1.5)

    # C+ should accumulate: each step adds (1.5 - 0.5) = 1.0
    # After 5 steps: C+ = 5.0, which exceeds h=4.5
    assert alarm is True
    assert state.upper > 4.5


def test_cusum_no_alarm_for_small_shifts():
    detector = CUSUMDetector(k=0.5, h=4.5)
    # Feed observations just below reference: z=0.3 < k=0.5
    for _ in range(20):
        state, alarm = detector.update(0.3)

    # Should never accumulate (max(0, 0 + 0.3 - 0.5) = 0)
    assert not alarm
    assert state.upper == 0.0


def test_cusum_reset():
    detector = CUSUMDetector(k=0.5, h=4.5)
    for _ in range(10):
        detector.update(2.0)
    detector.reset()
    assert detector.state.upper == 0.0
    assert detector.state.lower == 0.0
