import pytest

from app.forecasting.live_simulation import LiveSimulationInput, simulate_live


def test_same_seed_is_reproducible():
    state = LiveSimulationInput(
        minute=70, home_score=1, away_score=1, prematch_home_xg=1.4, prematch_away_xg=1.1
    )
    a = simulate_live(state, simulation_count=5000, seed=42)
    b = simulate_live(state, simulation_count=5000, seed=42)
    assert a == b
    assert sum(a.probabilities.as_tuple()) == pytest.approx(1.0)


def test_leading_late_team_has_higher_win_probability():
    state = LiveSimulationInput(
        minute=88, home_score=2, away_score=1, prematch_home_xg=1.3, prematch_away_xg=1.3
    )
    result = simulate_live(state, simulation_count=5000, seed=7)
    assert result.probabilities.home_win > 0.8
    assert result.expected_remaining_home_goals >= 0


def test_penalty_shootout_is_reproducible_and_normalized():
    from app.forecasting.live_simulation import simulate_penalty_shootout

    first = simulate_penalty_shootout(
        home_scored=1,
        away_scored=0,
        home_taken=1,
        away_taken=0,
        simulation_count=2000,
        seed=99,
    )
    second = simulate_penalty_shootout(
        home_scored=1,
        away_scored=0,
        home_taken=1,
        away_taken=0,
        simulation_count=2000,
        seed=99,
    )
    assert first == second
    assert first.home_advance + first.away_advance == pytest.approx(1.0)
    assert first.home_advance > 0.5
