from __future__ import annotations

from datetime import date
from typing import Protocol

from app.domain.entities import (
    Competition,
    Match,
    MatchEvent,
    MatchStatistics,
    ProviderCapabilities,
    Team,
)


class FootballProviderError(RuntimeError):
    pass


class ProviderRateLimited(FootballProviderError):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("provider rate limited")
        self.retry_after = retry_after


class ProviderUnavailable(FootballProviderError):
    pass


class FootballProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def list_competitions(self) -> list[Competition]: ...

    async def list_matches(
        self,
        *,
        competition_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
    ) -> list[Match]: ...

    async def get_match(self, match_id: str) -> Match: ...

    async def get_live_matches(self) -> list[Match]: ...

    async def get_match_events(self, match_id: str) -> list[MatchEvent]: ...

    async def get_match_statistics(self, match_id: str) -> MatchStatistics | None: ...

    async def get_lineups(self, match_id: str) -> list[dict]: ...

    async def get_team(self, team_id: str) -> Team: ...

    async def get_team_squad(self, team_id: str) -> list[dict]: ...

    async def get_player_availability(self, match_id: str) -> list[dict]: ...

    async def get_injuries(self, match_id: str) -> list[dict]: ...

    async def get_standings(self, competition_id: str) -> list[dict]: ...

    async def get_odds(self, match_id: str) -> list[dict]: ...

    async def get_provider_coverage(self) -> ProviderCapabilities: ...

    async def healthcheck(self) -> bool: ...
