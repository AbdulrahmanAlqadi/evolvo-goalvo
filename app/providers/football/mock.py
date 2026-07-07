from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.entities import (
    Competition,
    Match,
    MatchStatistics,
    ProviderCapabilities,
    Score,
    Team,
)
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.replay import ReplayFootballProvider


class MockFootballProvider(ReplayFootballProvider):
    name = "mock"
    capabilities = ProviderCapabilities(fixtures=True, live_events=False, statistics=True)

    def __init__(self) -> None:
        self.fixture_path = None
        competition = Competition(
            id="wc-2026", name="FIFA World Cup", name_ar="كأس العالم", season="2026"
        )
        self._mock_match = Match(
            id="demo-match-001",
            competition=competition,
            home_team=Team(id="arg", name="Argentina", name_ar="الأرجنتين", country_code="ARG"),
            away_team=Team(id="fra", name="France", name_ar="فرنسا", country_code="FRA"),
            kickoff=datetime.now(UTC) + timedelta(hours=2),
            status=MatchStatus.PRE_MATCH,
            stage=MatchStage.FINAL,
            neutral_venue=True,
            score=Score(),
        )

    async def list_competitions(self):
        return [self._mock_match.competition]

    async def list_matches(self, *, competition_id=None, date_from=None, date_to=None, status=None):
        return [self._mock_match]

    async def get_match(self, match_id):
        if match_id != self._mock_match.id:
            raise KeyError(match_id)
        return self._mock_match

    async def get_live_matches(self):
        return []

    async def get_match_events(self, match_id):
        await self.get_match(match_id)
        return []

    async def get_match_statistics(self, match_id):
        await self.get_match(match_id)
        return MatchStatistics(match_id=match_id, captured_at=datetime.now(UTC))

    async def get_lineups(self, match_id):
        return []

    async def get_team(self, team_id):
        return (
            self._mock_match.home_team
            if team_id == self._mock_match.home_team.id
            else self._mock_match.away_team
        )

    async def get_team_squad(self, team_id):
        return []

    async def get_player_availability(self, match_id):
        return []

    async def get_injuries(self, match_id):
        return []

    async def get_standings(self, competition_id):
        return []

    async def get_odds(self, match_id):
        return []

    async def get_provider_coverage(self):
        return self.capabilities

    async def healthcheck(self):
        return True
