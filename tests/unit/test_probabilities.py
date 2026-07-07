import math

import pytest

from app.domain.probabilities import OutcomeProbabilities, weighted_average


def test_normalization():
    p = OutcomeProbabilities(2, 1, 1).normalized()
    assert p.as_tuple() == pytest.approx((0.5, 0.25, 0.25))


def test_invalid_probability_rejected():
    with pytest.raises(ValueError):
        OutcomeProbabilities(math.nan, 0.5, 0.5).normalized()


def test_weighted_average_renormalizes_available_models():
    result = weighted_average(
        [
            (OutcomeProbabilities(0.6, 0.2, 0.2), 2),
            (OutcomeProbabilities(0.3, 0.3, 0.4), 1),
        ]
    )
    assert sum(result.as_tuple()) == pytest.approx(1.0)
    assert result.home_win == pytest.approx(0.5)
