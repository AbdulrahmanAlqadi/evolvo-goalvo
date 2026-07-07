from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.domain.entities import Competition, Match, ProviderCapabilities, Team
from app.providers.football.base import FootballProvider
from app.providers.football.entity_resolution import normalize_name

WORLD_CUP_NAME_AR = "كأس العالم"


@dataclass(frozen=True, slots=True)
class TeamLocalization:
    name_ar: str
    canonical_id: str | None = None
    country_code: str | None = None
    aliases: tuple[str, ...] = ()
    provider_ids: dict[str, str] | None = None


class ArabicTeamLocalizer:
    def __init__(self, entries: list[TeamLocalization]) -> None:
        self.by_country_code = {
            entry.country_code.upper(): entry
            for entry in entries
            if entry.country_code
        }
        self.by_alias = {
            normalize_name(alias): entry
            for entry in entries
            for alias in (entry.aliases or ())
        }
        self.by_canonical_id = {
            entry.canonical_id: entry
            for entry in entries
            if entry.canonical_id
        }
        self.by_provider_id = {
            (provider, provider_id): entry
            for entry in entries
            for provider, provider_id in (entry.provider_ids or {}).items()
        }

    @classmethod
    def from_path(cls, path: Path) -> ArabicTeamLocalizer:
        if not path.exists():
            return cls([])
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            TeamLocalization(
                name_ar=item["name_ar"],
                canonical_id=item.get("canonical_id"),
                country_code=item.get("country_code"),
                aliases=tuple(item.get("aliases") or ()),
                provider_ids=item.get("provider_ids") or {},
            )
            for item in payload.get("teams", [])
            if item.get("name_ar")
        ]
        return cls(entries)

    def localize(self, team: Team) -> Team:
        entry = None
        for provider, provider_id in team.provider_ids.items():
            entry = self.by_provider_id.get((provider, provider_id))
            if entry:
                break
        if entry is None and team.country_code:
            entry = self.by_country_code.get(team.country_code.upper())
        if entry is None:
            entry = self.by_canonical_id.get(team.id)
        if entry is None:
            entry = self.by_alias.get(normalize_name(team.name))
        if entry is None:
            return team
        return team.model_copy(update={"name_ar": entry.name_ar})


class WorldCupScope:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.world_cup_only
        self.allowed_ids = settings.world_cup_competition_id_set
        self.allowed_aliases = {
            normalize_name(alias) for alias in settings.world_cup_competition_alias_list
        }
        self.localizer = ArabicTeamLocalizer.from_path(settings.team_localization_path)

    def _competition_tokens(self, competition: Competition) -> set[str]:
        tokens = {competition.id}
        for provider, provider_id in competition.provider_ids.items():
            tokens.add(f"{provider}:{provider_id}")
            tokens.add(provider_id)
        return tokens

    def is_world_cup_competition(self, competition: Competition) -> bool:
        if not self.enabled:
            return True
        if self._competition_tokens(competition) & self.allowed_ids:
            return True
        normalized = normalize_name(competition.name)
        if any(
            excluded in normalized
            for excluded in ("club world cup", "women", "u 17", "u17", "u 20", "u20")
        ):
            return False
        return any(
            normalized == alias or alias in normalized
            for alias in self.allowed_aliases
        )

    def localize_competition(self, competition: Competition) -> Competition:
        if not self.is_world_cup_competition(competition):
            return competition
        return competition.model_copy(update={"name_ar": competition.name_ar or WORLD_CUP_NAME_AR})

    def localize_match(self, match: Match) -> Match:
        if not self.is_world_cup_competition(match.competition):
            return match
        return match.model_copy(
            update={
                "competition": self.localize_competition(match.competition),
                "home_team": self.localizer.localize(match.home_team),
                "away_team": self.localizer.localize(match.away_team),
            }
        )


class WorldCupFootballProvider:
    name = "world_cup_scope"

    def __init__(self, provider: FootballProvider, settings: Settings) -> None:
        self.provider = provider
        self.scope = WorldCupScope(settings)
        self.capabilities: ProviderCapabilities = provider.capabilities
        self.providers = getattr(provider, "providers", [provider])

    def _filter_matches(self, matches: list[Match]) -> list[Match]:
        return [
            self.scope.localize_match(match)
            for match in matches
            if self.scope.is_world_cup_competition(match.competition)
        ]

    def _require_match(self, match: Match) -> Match:
        if not self.scope.is_world_cup_competition(match.competition):
            raise KeyError(match.id)
        return self.scope.localize_match(match)

    async def list_competitions(self) -> list[Competition]:
        return [
            self.scope.localize_competition(competition)
            for competition in await self.provider.list_competitions()
            if self.scope.is_world_cup_competition(competition)
        ]

    async def list_matches(
        self,
        *,
        competition_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
    ) -> list[Match]:
        matches = await self.provider.list_matches(
            competition_id=competition_id,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        return self._filter_matches(matches)

    async def get_match(self, match_id: str) -> Match:
        return self._require_match(await self.provider.get_match(match_id))

    async def get_live_matches(self) -> list[Match]:
        return self._filter_matches(await self.provider.get_live_matches())

    async def get_match_events(self, match_id: str):
        await self.get_match(match_id)
        return await self.provider.get_match_events(match_id)

    async def get_match_statistics(self, match_id: str):
        await self.get_match(match_id)
        return await self.provider.get_match_statistics(match_id)

    async def get_lineups(self, match_id: str):
        await self.get_match(match_id)
        return await self.provider.get_lineups(match_id)

    async def get_team(self, team_id: str) -> Team:
        return self.scope.localizer.localize(await self.provider.get_team(team_id))

    async def get_team_squad(self, team_id: str) -> list[dict]:
        return await self.provider.get_team_squad(team_id)

    async def get_player_availability(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return await self.provider.get_player_availability(match_id)

    async def get_injuries(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return await self.provider.get_injuries(match_id)

    async def get_standings(self, competition_id: str) -> list[dict]:
        return await self.provider.get_standings(competition_id)

    async def get_odds(self, match_id: str) -> list[dict]:
        await self.get_match(match_id)
        return await self.provider.get_odds(match_id)

    async def get_provider_coverage(self) -> ProviderCapabilities:
        return self.capabilities

    async def healthcheck(self) -> bool:
        return await self.provider.healthcheck()

    async def statuses(self) -> list[dict[str, Any]]:
        statuses = await self.provider.statuses()
        for status in statuses:
            status["world_cup_only"] = self.scope.enabled
        return statuses
