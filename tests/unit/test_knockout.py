import pytest

from app.domain.probabilities import OutcomeProbabilities
from app.forecasting.knockout import advancement_from_90_minutes, advancement_from_extra_time


def test_knockout_advancement_sums_to_one():
    result = advancement_from_90_minutes(OutcomeProbabilities(0.4, 0.35, 0.25))
    assert result.home_advance + result.away_advance == pytest.approx(1.0)
    assert result.extra_time == pytest.approx(0.35)
    assert result.penalties <= result.extra_time


def test_extra_time_advancement_uses_draw_as_shootout_mass():
    result = advancement_from_extra_time(OutcomeProbabilities(0.3, 0.5, 0.2))
    assert result.home_advance + result.away_advance == pytest.approx(1.0)
    assert result.extra_time == 1.0
    assert result.penalties == pytest.approx(0.5)
