from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.probabilities import OutcomeProbabilities


@dataclass(slots=True)
class EloConfig:
    initial_rating: float = 1500.0
    k_factor: float = 24.0
    home_advantage: float = 70.0
    regression_half_life_days: float = 730.0


@dataclass(slots=True)
class EloRating:
    value: float
    updated_at: datetime


@dataclass(slots=True)
class EloModel:
    config: EloConfig = field(default_factory=EloConfig)
    ratings: dict[str, EloRating] = field(default_factory=dict)

    def rating_at(self, team_id: str, at: datetime) -> float:
        record = self.ratings.get(team_id)
        if record is None:
            return self.config.initial_rating
        days = max(0.0, (at - record.updated_at).total_seconds() / 86400)
        weight = 0.5 ** (days / self.config.regression_half_life_days)
        return self.config.initial_rating + (record.value - self.config.initial_rating) * weight

    def expected_home_score(
        self, home_id: str, away_id: str, at: datetime, neutral: bool = True
    ) -> float:
        home = self.rating_at(home_id, at) + (0.0 if neutral else self.config.home_advantage)
        away = self.rating_at(away_id, at)
        return 1.0 / (1.0 + 10 ** ((away - home) / 400.0))

    @staticmethod
    def goal_difference_multiplier(goal_difference: int) -> float:
        difference = abs(goal_difference)
        if difference <= 1:
            return 1.0
        if difference == 2:
            return 1.5
        return (11.0 + difference) / 8.0

    def update(
        self,
        *,
        home_id: str,
        away_id: str,
        home_goals: int,
        away_goals: int,
        played_at: datetime,
        importance: float = 1.0,
        neutral: bool = True,
    ) -> None:
        expected = self.expected_home_score(home_id, away_id, played_at, neutral)
        actual = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        multiplier = self.goal_difference_multiplier(home_goals - away_goals)
        delta = self.config.k_factor * importance * multiplier * (actual - expected)
        home_before = self.rating_at(home_id, played_at)
        away_before = self.rating_at(away_id, played_at)
        self.ratings[home_id] = EloRating(home_before + delta, played_at)
        self.ratings[away_id] = EloRating(away_before - delta, played_at)

    def probabilities(
        self,
        home_id: str,
        away_id: str,
        at: datetime,
        neutral: bool = True,
        draw_base: float = 0.27,
    ) -> OutcomeProbabilities:
        expected = self.expected_home_score(home_id, away_id, at, neutral)
        closeness = 1.0 - abs(expected - 0.5) * 2.0
        draw = max(0.14, min(0.34, draw_base * (0.75 + 0.5 * closeness)))
        decisive = 1.0 - draw
        return OutcomeProbabilities(
            decisive * expected, draw, decisive * (1.0 - expected)
        ).normalized()
