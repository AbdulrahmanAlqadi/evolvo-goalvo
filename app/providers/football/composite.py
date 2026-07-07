from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.entities import ProviderCapabilities
from app.providers.football.base import FootballProvider, ProviderUnavailable


@dataclass(slots=True)
class CacheItem:
    value: Any
    expires_at: float


class CompositeFootballProvider:
    name = "composite"

    def __init__(
        self, providers: list[FootballProvider], *, static_ttl: int = 86400, fixture_ttl: int = 300
    ) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.static_ttl = static_ttl
        self.fixture_ttl = fixture_ttl
        self._cache: dict[str, CacheItem] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.capabilities = self._merge_capabilities()

    def _merge_capabilities(self) -> ProviderCapabilities:
        fields = ProviderCapabilities.model_fields
        merged = {
            name: any(getattr(provider.capabilities, name) for provider in self.providers)
            for name in fields
        }
        return ProviderCapabilities(**merged)

    async def _call(
        self, operation: str, *args: Any, capability: str | None = None, **kwargs: Any
    ) -> Any:
        errors: list[str] = []
        for provider in self.providers:
            if capability and not getattr(provider.capabilities, capability):
                continue
            method: Callable[..., Awaitable[Any]] = getattr(provider, operation)
            try:
                return await method(*args, **kwargs)
            except Exception as exc:
                errors.append(f"{provider.name}:{type(exc).__name__}")
        raise ProviderUnavailable(f"all providers failed for {operation}: {', '.join(errors)}")

    async def _cached(self, key: str, ttl: int, loader: Callable[[], Awaitable[Any]]) -> Any:
        current = self._cache.get(key)
        if current and current.expires_at > time.monotonic():
            return current.value
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            current = self._cache.get(key)
            if current and current.expires_at > time.monotonic():
                return current.value
            value = await loader()
            self._cache[key] = CacheItem(value=value, expires_at=time.monotonic() + ttl)
            return value

    async def list_competitions(self):
        return await self._cached(
            "competitions",
            self.static_ttl,
            lambda: self._call("list_competitions", capability="fixtures"),
        )

    async def list_matches(
        self,
        *,
        competition_id=None,
        date_from: date | None = None,
        date_to: date | None = None,
        status=None,
    ):
        key = f"matches:{competition_id}:{date_from}:{date_to}:{status}"
        return await self._cached(
            key,
            self.fixture_ttl,
            lambda: self._call(
                "list_matches",
                competition_id=competition_id,
                date_from=date_from,
                date_to=date_to,
                status=status,
                capability="fixtures",
            ),
        )

    async def get_match(self, match_id):
        return await self._cached(
            f"match:{match_id}",
            self.fixture_ttl,
            lambda: self._call("get_match", match_id, capability="fixtures"),
        )

    async def get_live_matches(self):
        return await self._call("get_live_matches", capability="live_events")

    async def get_match_events(self, match_id):
        return await self._call("get_match_events", match_id, capability="live_events")

    async def get_match_statistics(self, match_id):
        return await self._call("get_match_statistics", match_id, capability="statistics")

    async def get_lineups(self, match_id):
        return await self._call("get_lineups", match_id, capability="lineups")

    async def get_team(self, team_id):
        return await self._call("get_team", team_id, capability="fixtures")

    async def get_team_squad(self, team_id):
        return await self._call("get_team_squad", team_id, capability="squads")

    async def get_player_availability(self, match_id):
        return await self._call("get_player_availability", match_id, capability="injuries")

    async def get_injuries(self, match_id):
        return await self._call("get_injuries", match_id, capability="injuries")

    async def get_standings(self, competition_id):
        return await self._call("get_standings", competition_id, capability="standings")

    async def get_odds(self, match_id):
        return await self._call("get_odds", match_id, capability="odds")

    async def get_provider_coverage(self):
        return self.capabilities

    async def healthcheck(self) -> bool:
        results = await asyncio.gather(
            *(provider.healthcheck() for provider in self.providers), return_exceptions=True
        )
        return any(result is True for result in results)

    async def statuses(self) -> list[dict[str, Any]]:
        results = await asyncio.gather(
            *(provider.healthcheck() for provider in self.providers), return_exceptions=True
        )
        return [
            {
                "provider": provider.name,
                "healthy": result is True,
                "capabilities": provider.capabilities.model_dump(),
                "error": None
                if result is True
                else type(result).__name__
                if isinstance(result, Exception)
                else "healthcheck_failed",
            }
            for provider, result in zip(self.providers, results, strict=True)
        ]
