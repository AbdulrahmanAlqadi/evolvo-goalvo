from __future__ import annotations

from app.domain.probabilities import OutcomeProbabilities


def devig_decimal_odds(home: float, draw: float, away: float) -> OutcomeProbabilities:
    if min(home, draw, away) <= 1.0:
        raise ValueError("decimal odds must exceed 1")
    implied = [1 / home, 1 / draw, 1 / away]
    total = sum(implied)
    return OutcomeProbabilities(*(value / total for value in implied)).normalized()
