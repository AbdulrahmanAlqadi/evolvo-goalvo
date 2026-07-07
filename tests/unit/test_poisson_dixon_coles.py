import pytest

from app.forecasting.dixon_coles import apply_dixon_coles
from app.forecasting.poisson import forecast_poisson, probabilities_from_matrix, score_matrix


def test_poisson_matrix_and_outcomes_normalize():
    forecast = forecast_poisson(1.4, 1.1)
    assert sum(sum(row) for row in forecast.matrix) == pytest.approx(1.0)
    assert sum(forecast.probabilities.as_tuple()) == pytest.approx(1.0)
    assert forecast.scorelines[0].probability >= forecast.scorelines[-1].probability


def test_dixon_coles_changes_low_scores_but_normalizes():
    matrix = score_matrix(1.2, 1.0)
    corrected = apply_dixon_coles(matrix, 1.2, 1.0, -0.08)
    assert corrected[0][0] != matrix[0][0]
    assert sum(sum(row) for row in corrected) == pytest.approx(1.0)
    assert sum(probabilities_from_matrix(corrected).as_tuple()) == pytest.approx(1.0)
