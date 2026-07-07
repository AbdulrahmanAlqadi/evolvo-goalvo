from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.probabilities import OutcomeProbabilities


def poisson_pmf(goals: int, expected_goals: float) -> float:
    if goals < 0 or expected_goals < 0 or not math.isfinite(expected_goals):
        raise ValueError("invalid Poisson input")
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


@dataclass(frozen=True, slots=True)
class ScorelineProbability:
    home_goals: int
    away_goals: int
    probability: float


@dataclass(slots=True)
class PoissonForecast:
    home_xg: float
    away_xg: float
    probabilities: OutcomeProbabilities
    scorelines: list[ScorelineProbability]
    matrix: list[list[float]]


def score_matrix(home_xg: float, away_xg: float, max_goals: int = 10) -> list[list[float]]:
    if home_xg < 0 or away_xg < 0:
        raise ValueError("expected goals cannot be negative")
    matrix = [
        [poisson_pmf(i, home_xg) * poisson_pmf(j, away_xg) for j in range(max_goals + 1)]
        for i in range(max_goals + 1)
    ]
    total = sum(sum(row) for row in matrix)
    return [[value / total for value in row] for row in matrix]


def probabilities_from_matrix(matrix: list[list[float]]) -> OutcomeProbabilities:
    home = draw = away = 0.0
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if i > j:
                home += value
            elif i == j:
                draw += value
            else:
                away += value
    return OutcomeProbabilities(home, draw, away).normalized()


def forecast_poisson(
    home_xg: float, away_xg: float, max_goals: int = 10, top_n: int = 5
) -> PoissonForecast:
    matrix = score_matrix(home_xg, away_xg, max_goals)
    ranked = sorted(
        (
            ScorelineProbability(i, j, matrix[i][j])
            for i in range(len(matrix))
            for j in range(len(matrix[i]))
        ),
        key=lambda item: item.probability,
        reverse=True,
    )[:top_n]
    return PoissonForecast(home_xg, away_xg, probabilities_from_matrix(matrix), ranked, matrix)
