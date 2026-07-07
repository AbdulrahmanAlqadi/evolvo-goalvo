from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutcomeProbabilities:
    home_win: float
    draw: float
    away_win: float

    def normalized(self) -> OutcomeProbabilities:
        values = [self.home_win, self.draw, self.away_win]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("probabilities must be finite and non-negative")
        total = sum(values)
        if total <= 0:
            raise ValueError("probability sum must be positive")
        return OutcomeProbabilities(*(v / total for v in values))

    def as_tuple(self) -> tuple[float, float, float]:
        normalized = self.normalized()
        return normalized.home_win, normalized.draw, normalized.away_win


def weighted_average(
    items: Iterable[tuple[OutcomeProbabilities, float]],
) -> OutcomeProbabilities:
    home = draw = away = total_weight = 0.0
    for probability, weight in items:
        if weight <= 0:
            continue
        p = probability.normalized()
        home += p.home_win * weight
        draw += p.draw * weight
        away += p.away_win * weight
        total_weight += weight
    if total_weight <= 0:
        raise ValueError("at least one positive model weight is required")
    return OutcomeProbabilities(
        home / total_weight, draw / total_weight, away / total_weight
    ).normalized()
