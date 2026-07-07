from __future__ import annotations

from app.core.config import Settings
from app.providers.football.api_football import ApiFootballProvider
from app.providers.football.composite import CompositeFootballProvider
from app.providers.football.football_data_org import FootballDataOrgProvider
from app.providers.football.mock import MockFootballProvider
from app.providers.football.replay import ReplayFootballProvider
from app.providers.football.thesportsdb import TheSportsDbProvider
from app.providers.football.world_cup_scope import WorldCupFootballProvider
from app.providers.football.worldcup26 import WorldCup26Provider


def build_single_provider(name: str, settings: Settings):
    if name == "replay":
        return ReplayFootballProvider(settings.replay_fixture_path)
    if name == "mock":
        return MockFootballProvider()
    if name == "worldcup26":
        return WorldCup26Provider(settings)
    if name == "api_football":
        return ApiFootballProvider(settings)
    if name == "football_data_org":
        return FootballDataOrgProvider(settings)
    if name == "thesportsdb":
        return TheSportsDbProvider(settings)
    raise ValueError(f"unsupported football provider: {name}")


def build_football_provider(
    settings: Settings,
) -> CompositeFootballProvider | WorldCupFootballProvider:
    names = [settings.football_provider, *settings.football_fallback_list]
    providers = []
    for name in dict.fromkeys(names):
        if name == "api_football" and not settings.api_football_key:
            continue
        if name == "football_data_org" and not settings.football_data_org_key:
            continue
        providers.append(build_single_provider(name, settings))
    if not providers:
        providers = [MockFootballProvider()]
    provider = CompositeFootballProvider(
        providers,
        static_ttl=settings.cache_static_ttl_seconds,
        fixture_ttl=settings.cache_fixtures_ttl_seconds,
    )
    if settings.world_cup_only:
        return WorldCupFootballProvider(provider, settings)
    return provider
