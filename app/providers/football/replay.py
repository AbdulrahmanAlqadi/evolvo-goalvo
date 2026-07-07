from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.domain.entities import (
    Competition,
    Match,
    MatchEvent,
    MatchStatistics,
    ProviderCapabilities,
    Team,
)
from app.providers.football.base import ProviderUnavailable


class ReplayFootballProvider:
    name = "replay"
    capabilities = ProviderCapabilities(
        fixtures=True,
        live_events=True,
        lineups=True,
        injuries=True,
        statistics=True,
        expected_goals=True,
        odds=False,
        standings=False,
        squads=True,
    )

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self._payload = self._load()

    def _load(self) -> dict:
        if not self.fixture_path.exists():
            raise ProviderUnavailable(f"replay fixture not found: {self.fixture_path}")
        return json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def _competition(self) -> Competition:
        return Competition.model_validate(self._payload["competition"])

    def _team(self, key: str) -> Team:
        return Team.model_validate(self._payload[key])

    def _match(self) -> Match:
        raw = dict(self._payload["match"])
        raw["competition"] = self._competition()
        raw["home_team"] = self._team("home_team")
        raw["away_team"] = self._team("away_team")
        return Match.model_validate(raw)

    async def list_competitions(self) -> list[Competition]:
        return [self._competition()]

    async def list_matches(
        self,
        *,
        competition_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
    ) -> list[Match]:
        match = self._match()
        if competition_id and match.competition.id != competition_id:
            return []
        if date_from and match.kickoff.date() < date_from:
            return []
        if date_to and match.kickoff.date() > date_to:
            return []
        if status and match.status.value != status:
            return []
        return [match]

    async def get_match(self, match_id: str) -> Match:
        match = self._match()
        if match.id != match_id:
            raise ProviderUnavailable("match not present in replay fixture")
        return match

    async def get_live_matches(self) -> list[Match]:
        match = self._match()
        return [match] if match.status.value in {"LIVE", "EXTRA_TIME", "PENALTIES"} else []

    async def get_match_events(self, match_id: str) -> list[MatchEvent]:
        await self.get_match(match_id)
        return [MatchEvent.model_validate(item) for item in self._payload.get("events", [])]

    async def get_match_statistics(self, match_id: str) -> MatchStatistics | None:
        await self.get_match(match_id)
        raw = self._payload.get("statistics")
        return MatchStatistics.model_validate(raw) if raw else None

    async def get_lineups(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return list(self._payload.get("lineups", []))

    async def get_team(self, team_id: str) -> Team:
        for key in ("home_team", "away_team"):
            team = self._team(key)
            if team.id == team_id:
                return team
        raise ProviderUnavailable("team not found")

    async def get_team_squad(self, team_id: str) -> list[dict]:
        await self.get_team(team_id)
        return [item for item in self._payload.get("squads", []) if item.get("team_id") == team_id]

    async def get_player_availability(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return list(self._payload.get("availability", []))

    async def get_injuries(self, match_id: str) -> list[dict]:
        return await self.get_player_availability(match_id)

    async def get_standings(self, competition_id: str) -> list[dict]:
        return []

    async def get_odds(self, match_id: str) -> list[dict]:
        return []

    async def get_provider_coverage(self) -> ProviderCapabilities:
        return self.capabilities

    async def healthcheck(self) -> bool:
        return self.fixture_path.exists()

    def events_until(self, index: int) -> list[MatchEvent]:
        return [MatchEvent.model_validate(item) for item in self._payload.get("events", [])[:index]]
