import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.forecasting.live_simulation import LiveSimulationInput, simulate_live
from app.forecasting.poisson import forecast_poisson


@given(
    home_xg=st.floats(min_value=0.05, max_value=5, allow_nan=False, allow_infinity=False),
    away_xg=st.floats(min_value=0.05, max_value=5, allow_nan=False, allow_infinity=False),
)
def test_poisson_probability_invariants(home_xg, away_xg):
    values = forecast_poisson(home_xg, away_xg, max_goals=12).probabilities.as_tuple()
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in values)
    assert sum(values) == pytest.approx(1.0)


@given(
    minute=st.integers(min_value=0, max_value=90),
    home_score=st.integers(min_value=0, max_value=6),
    away_score=st.integers(min_value=0, max_value=6),
)
def test_live_probability_invariants(minute, home_score, away_score):
    result = simulate_live(
        LiveSimulationInput(
            minute=minute,
            home_score=home_score,
            away_score=away_score,
            prematch_home_xg=1.4,
            prematch_away_xg=1.2,
        ),
        simulation_count=1000,
        seed=123,
    )
    values = result.probabilities.as_tuple()
    assert all(0 <= value <= 1 for value in values)
    assert sum(values) == pytest.approx(1.0)
