from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.domain.entities import (
    Competition,
    Match,
    MatchEvent,
    ProviderCapabilities,
    Score,
    Team,
)
from app.domain.enums import EventType, MatchStage, MatchStatus, TeamSide
from app.providers.football.http import SafeHttpProvider

_STAGE_MAP = {
    "group": MatchStage.GROUP,
    "r32": MatchStage.ROUND_OF_32,
    "r16": MatchStage.ROUND_OF_16,
    "qf": MatchStage.QUARTER_FINAL,
    "sf": MatchStage.SEMI_FINAL,
    "third": MatchStage.THIRD_PLACE,
    "final": MatchStage.FINAL,
}
_MINUTE_PATTERN = re.compile(r"(?<!\d)(\d{1,3})(?:'\+|\+)?(\d{1,2})?")
_LIVE_INFERENCE_WINDOW = timedelta(minutes=150)
_MATCH_UTC_OFFSETS = {
    # worldcup26.ir exposes local stadium time without venue metadata.
    # These explicit July 2026 venue offsets prevent UTC misclassification.
    "93": -5,  # Arlington
    "94": -7,  # Seattle
    "95": -4,  # Atlanta
    "96": -7,  # Vancouver
    "97": -4,  # Boston
    "98": -7,  # Los Angeles
    "99": -4,  # Miami
    "100": -5,  # Kansas City
    "101": -5,  # Dallas/Arlington
    "102": -4,  # Atlanta
    "103": -4,  # Miami
    "104": -4,  # New York/New Jersey
}


class WorldCup26Provider(SafeHttpProvider):
    name = "worldcup26"
    capabilities = ProviderCapabilities(
        fixtures=True,
        live_events=True,
        lineups=False,
        injuries=False,
        statistics=False,
        expected_goals=False,
        odds=False,
        standings=False,
        squads=False,
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            base_url=settings.worldcup26_base_url,
            per_minute=60,
            per_day=5000,
        )

    @staticmethod
    def _score_value(value: Any) -> int:
        if value is None:
            return 0
        text = str(value).strip().lower()
        if text in {"", "null", "none"}:
            return 0
        return int(text)

    @staticmethod
    def _score_optional(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"", "null", "none"}:
            return None
        return int(text)

    @staticmethod
    def _scorer_minutes(value: Any) -> list[int]:
        text = str(value or "").strip()
        if text.lower() in {"", "null", "none"}:
            return []
        minutes: list[int] = []
        for match in _MINUTE_PATTERN.finditer(text):
            base = int(match.group(1))
            added = int(match.group(2) or 0)
            minute = base + added
            if 0 <= minute <= 150:
                minutes.append(minute)
        return minutes

    @staticmethod
    def _kickoff(value: str, match_id: str | None = None) -> datetime:
        naive = datetime.strptime(value, "%m/%d/%Y %H:%M")
        offset_hours = _MATCH_UTC_OFFSETS.get(str(match_id or ""))
        if offset_hours is not None:
            local_zone = timezone(timedelta(hours=offset_hours))
            return naive.replace(tzinfo=local_zone).astimezone(UTC)
        return naive.replace(tzinfo=UTC)

    @staticmethod
    def _status(item: dict[str, Any]) -> tuple[MatchStatus, int | None]:
        finished = str(item.get("finished", "")).strip().lower() == "true"
        elapsed = str(item.get("time_elapsed", "")).strip().lower()
        match_minute = str(item.get("match_minute", "")).strip().lower()
        if finished or elapsed == "finished":
            return MatchStatus.FINISHED, None
        if elapsed in {"", "null", "none", "notstarted", "not_started"}:
            return MatchStatus.PRE_MATCH, None
        if elapsed in {"halftime", "half_time", "ht"}:
            return MatchStatus.HALF_TIME, 45
        if elapsed in {"extra", "extra_time", "et"}:
            return MatchStatus.EXTRA_TIME, None
        if elapsed in {"penalties", "shootout"}:
            return MatchStatus.PENALTIES, None
        if match_minute.isdigit():
            return MatchStatus.LIVE, int(match_minute)
        if elapsed.isdigit():
            return MatchStatus.LIVE, int(elapsed)
        return MatchStatus.LIVE, None

    def _competition(self) -> Competition:
        return Competition(
            id="worldcup26:competition:2026",
            name="FIFA World Cup",
            name_ar="كأس العالم",
            season="2026",
            provider_ids={self.name: "2026"},
        )

    def _team(
        self,
        item: dict[str, Any],
        side: str,
        team_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> Team:
        provider_id = str(item[f"{side}_team_id"])
        fallback_name = (
            item.get(f"{side}_team_name_en")
            or item.get(f"{side}_team_label")
            or f"Unresolved {side.title()} Team"
        )
        if provider_id == "0":
            return Team(
                id=f"worldcup26:placeholder:{item['id']}:{side}",
                name=fallback_name,
            )
        team = (team_lookup or {}).get(provider_id, {})
        name = team.get("name_en") or fallback_name
        fifa_code = team.get("fifa_code")
        return Team(
            id=f"worldcup26:team:{provider_id}",
            name=name,
            country_code=str(fifa_code).upper() if fifa_code else None,
            provider_ids={self.name: provider_id},
        )

    @staticmethod
    def _infer_live_from_clock(
        status: MatchStatus,
        minute: int | None,
        *,
        kickoff: datetime,
        observed_at: datetime,
    ) -> tuple[MatchStatus, int | None]:
        if status != MatchStatus.PRE_MATCH:
            return status, minute
        elapsed_seconds = (observed_at - kickoff).total_seconds()
        if elapsed_seconds < 0 or elapsed_seconds > _LIVE_INFERENCE_WINDOW.total_seconds():
            return status, minute
        inferred_minute = max(1, min(120, int(elapsed_seconds // 60) + 1))
        return MatchStatus.LIVE, inferred_minute

    def _match(
        self,
        item: dict[str, Any],
        team_lookup: dict[str, dict[str, Any]] | None = None,
        observed_at: datetime | None = None,
    ) -> Match:
        status, minute = self._status(item)
        kickoff = self._kickoff(item["local_date"], str(item.get("id")))
        home_score = self._score_value(item.get("home_score"))
        away_score = self._score_value(item.get("away_score"))
        observed = (observed_at or datetime.now(UTC)).astimezone(UTC)
        status, minute = self._infer_live_from_clock(
            status, minute, kickoff=kickoff, observed_at=observed
        )
        return Match(
            id=f"worldcup26:game:{item['id']}",
            competition=self._competition(),
            home_team=self._team(item, "home", team_lookup),
            away_team=self._team(item, "away", team_lookup),
            kickoff=kickoff,
            status=status,
            stage=_STAGE_MAP.get(str(item.get("type", "")).lower(), MatchStage.OTHER),
            neutral_venue=True,
            minute=minute,
            period=str(item.get("time_elapsed") or ""),
            score=Score(
                home=home_score,
                away=away_score,
                home_penalties=self._score_optional(item.get("home_penalty_score")),
                away_penalties=self._score_optional(item.get("away_penalty_score")),
            ),
            updated_at=observed,
        )

    async def _games(self) -> list[dict[str, Any]]:
        payload = await self._request_json("list_matches", "GET", "/get/games")
        games = payload.get("games") or []
        return games if isinstance(games, list) else []

    async def _teams_by_id(self) -> dict[str, dict[str, Any]]:
        payload = await self._request_json("list_teams", "GET", "/get/teams")
        teams = payload.get("teams") or []
        if not isinstance(teams, list):
            return {}
        return {
            str(item["id"]): item
            for item in teams
            if isinstance(item, dict) and item.get("id")
        }

    async def _game(self, match_id: str) -> dict[str, Any]:
        provider_id = match_id.rsplit(":", 1)[-1]
        for item in await self._games():
            if str(item.get("id")) == provider_id:
                return item
        raise KeyError(match_id)

    async def list_competitions(self) -> list[Competition]:
        return [self._competition()]

    async def list_matches(
        self, *, competition_id=None, date_from=None, date_to=None, status=None
    ) -> list[Match]:
        games, teams = await asyncio.gather(self._games(), self._teams_by_id())
        matches = [self._match(item, teams) for item in games]
        if competition_id and competition_id not in {
            "worldcup26:competition:2026",
            "worldcup26:2026",
            "2026",
        }:
            return []
        if date_from:
            matches = [match for match in matches if match.kickoff.date() >= date_from]
        if date_to:
            matches = [match for match in matches if match.kickoff.date() <= date_to]
        if status:
            matches = [match for match in matches if match.status.value == status]
        return matches

    async def get_match(self, match_id: str) -> Match:
        game, teams = await asyncio.gather(self._game(match_id), self._teams_by_id())
        return self._match(game, teams)

    async def get_live_matches(self) -> list[Match]:
        live_statuses = {
            MatchStatus.LIVE,
            MatchStatus.HALF_TIME,
            MatchStatus.EXTRA_TIME,
            MatchStatus.PENALTIES,
        }
        return [
            match
            for match in await self.list_matches()
            if match.status in live_statuses
        ]

    async def get_match_events(self, match_id: str) -> list[MatchEvent]:
        game, teams = await asyncio.gather(self._game(match_id), self._teams_by_id())
        match = self._match(game, teams)
        events: list[MatchEvent] = []
        fallback_minute = match.minute or (90 if match.status == MatchStatus.FINISHED else 0)
        home_minutes = self._scorer_minutes(game.get("home_scorers"))
        away_minutes = self._scorer_minutes(game.get("away_scorers"))
        for index in range(match.score.home):
            minute = home_minutes[index] if index < len(home_minutes) else fallback_minute
            events.append(
                MatchEvent(
                    id=f"{match.id}:score-home-{index + 1}",
                    match_id=match.id,
                    provider=self.name,
                    provider_event_id=f"{match.id}:score-home-{index + 1}",
                    type=EventType.GOAL,
                    side=TeamSide.HOME,
                    minute=minute,
                    occurred_at=match.updated_at,
                    received_at=match.updated_at,
                    payload={"source": "scoreboard", "raw_scorers": game.get("home_scorers")},
                )
            )
        for index in range(match.score.away):
            minute = away_minutes[index] if index < len(away_minutes) else fallback_minute
            events.append(
                MatchEvent(
                    id=f"{match.id}:score-away-{index + 1}",
                    match_id=match.id,
                    provider=self.name,
                    provider_event_id=f"{match.id}:score-away-{index + 1}",
                    type=EventType.GOAL,
                    side=TeamSide.AWAY,
                    minute=minute,
                    occurred_at=match.updated_at,
                    received_at=match.updated_at,
                    payload={"source": "scoreboard", "raw_scorers": game.get("away_scorers")},
                )
            )
        return events

    async def get_match_statistics(self, match_id: str):
        await self.get_match(match_id)
        return None

    async def get_lineups(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return []

    async def get_team(self, team_id: str) -> Team:
        provider_id = team_id.rsplit(":", 1)[-1]
        teams = await self._teams_by_id()
        team = teams.get(provider_id)
        if team:
            return Team(
                id=f"worldcup26:team:{provider_id}",
                name=team.get("name_en") or provider_id,
                country_code=str(team["fifa_code"]).upper() if team.get("fifa_code") else None,
                provider_ids={self.name: provider_id},
            )
        raise KeyError(team_id)

    async def get_team_squad(self, team_id: str) -> list[dict]:
        await self.get_team(team_id)
        return []

    async def get_player_availability(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return []

    async def get_injuries(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return []

    async def get_standings(self, competition_id: str) -> list[dict]:
        return []

    async def get_odds(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return []

    async def get_provider_coverage(self) -> ProviderCapabilities:
        return self.capabilities

    async def healthcheck(self) -> bool:
        try:
            return bool(await self._games())
        except Exception:
            return False
