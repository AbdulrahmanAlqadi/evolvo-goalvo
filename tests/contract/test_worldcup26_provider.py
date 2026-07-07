from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.domain.enums import MatchStage, MatchStatus
from app.providers.football.worldcup26 import WorldCup26Provider

_GAME = {
    "id": "93",
    "home_team_id": "41",
    "away_team_id": "29",
    "home_score": "null",
    "away_score": "null",
    "local_date": "07/06/2026 14:00",
    "finished": "FALSE",
    "time_elapsed": "notstarted",
    "type": "r16",
    "home_penalty_score": "null",
    "away_penalty_score": "null",
    "home_team_name_en": "Portugal",
    "away_team_name_en": "Spain",
}

_TEAMS = {
    "41": {"id": "41", "name_en": "Portugal", "fifa_code": "POR"},
    "29": {"id": "29", "name_en": "Spain", "fifa_code": "ESP"},
}


@pytest.mark.asyncio
async def test_worldcup26_provider_maps_fixture_with_provider_ids(monkeypatch):
    provider = WorldCup26Provider(Settings(football_provider="worldcup26"))

    async def fake_games():
        return [_GAME]

    async def fake_teams():
        return _TEAMS

    monkeypatch.setattr(provider, "_games", fake_games)
    monkeypatch.setattr(provider, "_teams_by_id", fake_teams)

    try:
        matches = await provider.list_matches()
        match = matches[0]

        assert match.id == "worldcup26:game:93"
        assert match.competition.provider_ids == {"worldcup26": "2026"}
        assert match.stage == MatchStage.ROUND_OF_16
        assert match.status == MatchStatus.PRE_MATCH
        assert match.kickoff == datetime(2026, 7, 6, 19, 0, tzinfo=UTC)
        assert match.home_team.provider_ids == {"worldcup26": "41"}
        assert match.away_team.provider_ids == {"worldcup26": "29"}
        assert match.home_team.country_code == "POR"
        assert match.away_team.country_code == "ESP"
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_worldcup26_provider_infers_live_when_upstream_status_is_stale():
    provider = WorldCup26Provider(Settings(football_provider="worldcup26"))
    game = {
        **_GAME,
        "id": "94",
        "local_date": "07/06/2026 17:00",
        "home_team_name_en": "United States",
        "away_team_name_en": "Belgium",
    }

    try:
        match = provider._match(
            game,
            _TEAMS,
            observed_at=datetime(2026, 7, 7, 0, 32, tzinfo=UTC),
        )

        assert match.kickoff == datetime(2026, 7, 7, 0, 0, tzinfo=UTC)
        assert match.status == MatchStatus.LIVE
        assert match.minute == 33
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_worldcup26_provider_reconstructs_goal_events_from_scorers(monkeypatch):
    provider = WorldCup26Provider(Settings(football_provider="worldcup26"))
    game = {
        **_GAME,
        "id": "94",
        "home_score": "2",
        "away_score": "1",
        "finished": "TRUE",
        "time_elapsed": "finished",
        "home_scorers": "Player A 45'+5', Player B 90+4'",
        "away_scorers": "Player C 125(P)",
    }

    async def fake_games():
        return [game]

    async def fake_teams():
        return _TEAMS

    monkeypatch.setattr(provider, "_games", fake_games)
    monkeypatch.setattr(provider, "_teams_by_id", fake_teams)

    try:
        events = await provider.get_match_events("worldcup26:game:94")

        assert [event.minute for event in events] == [50, 94, 125]
        assert [event.side.value for event in events] == ["HOME", "HOME", "AWAY"]
        assert all(event.payload["source"] == "scoreboard" for event in events)
    finally:
        await provider.close()
