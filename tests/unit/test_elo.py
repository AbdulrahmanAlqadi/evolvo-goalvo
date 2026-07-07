from datetime import UTC, datetime, timedelta

from app.forecasting.elo import EloModel, EloRating


def test_elo_update_is_zero_sum_for_pair():
    at = datetime(2026, 1, 1, tzinfo=UTC)
    model = EloModel()
    model.ratings["a"] = EloRating(1500, at)
    model.ratings["b"] = EloRating(1500, at)
    model.update(home_id="a", away_id="b", home_goals=2, away_goals=0, played_at=at, neutral=True)
    assert model.ratings["a"].value + model.ratings["b"].value == 3000
    assert model.ratings["a"].value > 1500


def test_inactivity_regresses_to_mean():
    at = datetime(2020, 1, 1, tzinfo=UTC)
    model = EloModel()
    model.ratings["a"] = EloRating(1800, at)
    later = model.rating_at("a", at + timedelta(days=730))
    assert later == 1650
