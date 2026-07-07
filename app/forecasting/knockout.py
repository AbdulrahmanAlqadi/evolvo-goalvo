from __future__ import annotations

from dataclasses import dataclass

from app.domain.probabilities import OutcomeProbabilities


@dataclass(frozen=True, slots=True)
class KnockoutProbabilities:
    home_advance: float
    away_advance: float
    extra_time: float
    penalties: float


def advancement_from_90_minutes(
    outcomes: OutcomeProbabilities,
    *,
    extra_time_home_strength: float = 0.5,
    penalty_home_strength: float = 0.5,
    extra_time_draw_probability: float = 0.58,
) -> KnockoutProbabilities:
    p = outcomes.normalized()
    et_home_win = (1.0 - extra_time_draw_probability) * extra_time_home_strength
    et_away_win = (1.0 - extra_time_draw_probability) * (1.0 - extra_time_home_strength)
    penalty_probability = p.draw * extra_time_draw_probability
    home = p.home_win + p.draw * (et_home_win + extra_time_draw_probability * penalty_home_strength)
    away = p.away_win + p.draw * (
        et_away_win + extra_time_draw_probability * (1.0 - penalty_home_strength)
    )
    total = home + away
    return KnockoutProbabilities(home / total, away / total, p.draw, penalty_probability)


def advancement_from_extra_time(
    end_of_extra_time: OutcomeProbabilities,
    *,
    penalty_home_strength: float = 0.5,
) -> KnockoutProbabilities:
    p = end_of_extra_time.normalized()
    home = p.home_win + p.draw * penalty_home_strength
    away = p.away_win + p.draw * (1.0 - penalty_home_strength)
    total = home + away
    return KnockoutProbabilities(
        home_advance=home / total,
        away_advance=away / total,
        extra_time=1.0,
        penalties=p.draw,
    )
