from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.domain.entities import Match, Team
from app.domain.enums import MatchStage, MatchStatus
from app.forecasting.elo import EloModel, EloRating


@dataclass(frozen=True, slots=True)
class TeamStrengthProfile:
    key: str
    elo: float
    attack: float
    defence: float
    matches_played: int
    goals_for: int
    goals_against: int
    source: str
    rest_days: float | None = None
    opponent_average_elo: float | None = None
    opponent_adjusted_form: float | None = None
    weighted_result_points: float = 0.0
    fatigue_penalty: float = 0.0
    prior_source: str | None = None

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def team_strength_key(team: Team) -> str:
    if team.country_code:
        return team.country_code.upper()
    return team.id


def profile_lookup_keys(team: Team) -> tuple[str, ...]:
    keys = [team.id]
    if team.country_code:
        keys.extend([team.country_code, team.country_code.lower(), team.country_code.upper()])
    for provider, provider_id in team.provider_ids.items():
        keys.extend([f"{provider}:{provider_id}", provider_id])
    return tuple(dict.fromkeys(item for item in keys if item))


def _base_profile(team: Team, configured_profiles: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized_profiles = {key.casefold(): value for key, value in configured_profiles.items()}
    raw = None
    for key in profile_lookup_keys(team):
        raw = normalized_profiles.get(key.casefold())
        if raw:
            break
    if not isinstance(raw, dict):
        return {"elo": 1500.0, "attack": 1.0, "defence": 1.0}, False
    return (
        {
            "elo": float(raw.get("elo", 1500.0)),
            "attack": float(raw.get("attack", 1.0)),
            "defence": float(raw.get("defence", 1.0)),
            "source": str(raw.get("source") or "configured_prior"),
        },
        True,
    )


def _is_concrete_team(team: Team) -> bool:
    return bool(team.country_code or team.provider_ids) and "placeholder" not in team.id


def _stage_importance(stage: MatchStage) -> float:
    return {
        MatchStage.GROUP: 1.0,
        MatchStage.ROUND_OF_32: 1.25,
        MatchStage.ROUND_OF_16: 1.4,
        MatchStage.QUARTER_FINAL: 1.55,
        MatchStage.SEMI_FINAL: 1.7,
        MatchStage.THIRD_PLACE: 1.3,
        MatchStage.FINAL: 1.9,
    }.get(stage, 1.0)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _history_available_at(match: Match) -> datetime:
    return match.kickoff + timedelta(hours=3)


def _eligible_history(
    target_match: Match,
    historical_matches: list[Match],
    prediction_time: datetime,
) -> list[Match]:
    return sorted(
        [
            match
            for match in historical_matches
            if match.id != target_match.id
            and match.status == MatchStatus.FINISHED
            and match.kickoff < target_match.kickoff
            and _history_available_at(match) <= prediction_time
            and _is_concrete_team(match.home_team)
            and _is_concrete_team(match.away_team)
        ],
        key=lambda item: item.kickoff,
    )


def build_team_strength_profiles(
    target_match: Match,
    *,
    historical_matches: list[Match],
    prediction_time: datetime,
    configured_profiles: dict[str, Any],
) -> tuple[TeamStrengthProfile, TeamStrengthProfile, list[Match]]:
    eligible = _eligible_history(target_match, historical_matches, prediction_time)
    elo = EloModel()
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "played": 0,
            "gf": 0,
            "ga": 0,
            "last_played_at": None,
            "opponent_elo_sum": 0.0,
            "result_points": 0.0,
        }
    )

    def ensure_seed(team: Team, at: datetime) -> None:
        key = team_strength_key(team)
        if key in elo.ratings:
            return
        base, _configured = _base_profile(team, configured_profiles)
        elo.ratings[key] = EloRating(base["elo"], at)

    for match in eligible:
        home_key = team_strength_key(match.home_team)
        away_key = team_strength_key(match.away_team)
        ensure_seed(match.home_team, match.kickoff)
        ensure_seed(match.away_team, match.kickoff)
        home_before = elo.rating_at(home_key, match.kickoff)
        away_before = elo.rating_at(away_key, match.kickoff)
        if match.score.home > match.score.away:
            home_result = 1.0
        elif match.score.home == match.score.away:
            home_result = 0.5
        else:
            home_result = 0.0
        away_result = 1.0 - home_result if home_result != 0.5 else 0.5
        recency_days = max(0.0, (target_match.kickoff - match.kickoff).total_seconds() / 86400)
        recency_weight = 0.5 ** (recency_days / 180.0)
        importance = _stage_importance(match.stage)
        elo.update(
            home_id=home_key,
            away_id=away_key,
            home_goals=match.score.home,
            away_goals=match.score.away,
            played_at=match.kickoff,
            importance=importance,
            neutral=match.neutral_venue,
        )
        stats[home_key]["played"] += 1
        stats[home_key]["gf"] += match.score.home
        stats[home_key]["ga"] += match.score.away
        stats[home_key]["last_played_at"] = match.kickoff
        stats[home_key]["opponent_elo_sum"] += away_before
        stats[home_key]["result_points"] += home_result * recency_weight * importance
        stats[away_key]["played"] += 1
        stats[away_key]["gf"] += match.score.away
        stats[away_key]["ga"] += match.score.home
        stats[away_key]["last_played_at"] = match.kickoff
        stats[away_key]["opponent_elo_sum"] += home_before
        stats[away_key]["result_points"] += away_result * recency_weight * importance

    total_team_matches = sum(item["played"] for item in stats.values())
    total_goals = sum(item["gf"] for item in stats.values())
    average_goals = total_goals / total_team_matches if total_team_matches else 1.25

    def finalize(team: Team) -> TeamStrengthProfile:
        key = team_strength_key(team)
        ensure_seed(team, prediction_time)
        base, configured = _base_profile(team, configured_profiles)
        team_stats = stats[key]
        played = int(team_stats["played"])
        gf = int(team_stats["gf"])
        ga = int(team_stats["ga"])
        if played:
            prior_source = str(base.get("source") or "configured_prior") if configured else None
            opponent_average_elo = float(team_stats["opponent_elo_sum"]) / played
            opponent_attack_factor = _clip(opponent_average_elo / 1500.0, 0.85, 1.20)
            opponent_defence_factor = _clip(1500.0 / opponent_average_elo, 0.85, 1.20)
            attack_form = _clip((gf / played) / average_goals, 0.55, 1.65)
            defence_form = _clip((ga / played) / average_goals, 0.55, 1.65)
            attack_form = _clip(attack_form * opponent_attack_factor, 0.55, 1.75)
            defence_form = _clip(defence_form * opponent_defence_factor, 0.50, 1.75)
            blend = min(0.72, 0.18 * played)
            attack = base["attack"] * (1.0 - blend) + attack_form * blend
            defence = base["defence"] * (1.0 - blend) + defence_form * blend
            source = "tournament_results+configured_prior" if configured else "tournament_results"
            last_played_at = team_stats["last_played_at"]
            rest_days = (
                (target_match.kickoff - last_played_at).total_seconds() / 86400
                if last_played_at
                else None
            )
            fatigue_penalty = (
                0.04
                if rest_days is not None and rest_days < 3.0
                else 0.02
                if rest_days is not None and rest_days < 4.0
                else 0.0
            )
            attack = max(0.45, attack - fatigue_penalty)
            opponent_adjusted_form = float(team_stats["result_points"]) / played
        else:
            attack = base["attack"]
            defence = base["defence"]
            source = "configured_prior" if configured else "default_prior"
            prior_source = str(base.get("source") or "configured_prior") if configured else None
            rest_days = None
            opponent_average_elo = None
            opponent_adjusted_form = None
            fatigue_penalty = 0.0
        return TeamStrengthProfile(
            key=key,
            elo=elo.rating_at(key, prediction_time),
            attack=_clip(attack, 0.45, 1.85),
            defence=_clip(defence, 0.45, 1.85),
            matches_played=played,
            goals_for=gf,
            goals_against=ga,
            source=source,
            rest_days=rest_days,
            opponent_average_elo=opponent_average_elo,
            opponent_adjusted_form=opponent_adjusted_form,
            weighted_result_points=float(team_stats["result_points"]),
            fatigue_penalty=fatigue_penalty,
            prior_source=prior_source,
        )

    return finalize(target_match.home_team), finalize(target_match.away_team), eligible
