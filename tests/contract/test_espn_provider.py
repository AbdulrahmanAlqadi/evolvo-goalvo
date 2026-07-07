import pytest

from app.core.config import Settings
from app.providers.football.espn import EspnFootballProvider


@pytest.mark.asyncio
async def test_espn_provider_maps_live_team_statistics(monkeypatch):
    provider = EspnFootballProvider(
        Settings(
            football_provider="espn",
            espn_match_id_map='{"worldcup26:game:94":"760507"}',
        )
    )

    async def fake_summary(_event_id):
        return {
            "boxscore": {
                "teams": [
                    {
                        "statistics": [
                            {"name": "foulsCommitted", "displayValue": "1"},
                            {"name": "yellowCards", "displayValue": "0"},
                            {"name": "redCards", "displayValue": "0"},
                            {"name": "offsides", "displayValue": "0"},
                            {"name": "wonCorners", "displayValue": "0"},
                            {"name": "saves", "displayValue": "2"},
                            {"name": "possessionPct", "displayValue": "33.8"},
                            {"name": "totalShots", "displayValue": "0"},
                            {"name": "shotsOnTarget", "displayValue": "0"},
                            {"name": "totalPasses", "displayValue": "26"},
                            {"name": "passPct", "displayValue": "0.88"},
                        ]
                    },
                    {
                        "statistics": [
                            {"name": "foulsCommitted", "displayValue": "0"},
                            {"name": "yellowCards", "displayValue": "0"},
                            {"name": "redCards", "displayValue": "0"},
                            {"name": "offsides", "displayValue": "0"},
                            {"name": "wonCorners", "displayValue": "1"},
                            {"name": "saves", "displayValue": "0"},
                            {"name": "possessionPct", "displayValue": "66.2"},
                            {"name": "totalShots", "displayValue": "7"},
                            {"name": "shotsOnTarget", "displayValue": "3"},
                            {"name": "totalPasses", "displayValue": "39"},
                            {"name": "passPct", "displayValue": "0.82"},
                        ]
                    },
                ]
            }
        }

    monkeypatch.setattr(provider, "_summary", fake_summary)

    try:
        stats = await provider.get_match_statistics("worldcup26:game:94")
    finally:
        await provider.close()

    assert stats is not None
    assert stats.possession_home == 33.8
    assert stats.possession_away == 66.2
    assert stats.shots_home == 0
    assert stats.shots_away == 7
    assert stats.shots_on_target_away == 3
    assert stats.passes_home == 26
    assert stats.passes_away == 39
    assert stats.pass_accuracy_home == 88
    assert stats.pass_accuracy_away == 82
    assert stats.corners_away == 1
    assert stats.fouls_home == 1
    assert stats.saves_home == 2


@pytest.mark.asyncio
async def test_espn_provider_healthcheck_uses_explicit_event_mapping(monkeypatch):
    provider = EspnFootballProvider(
        Settings(
            football_provider="espn",
            espn_match_id_map='{"worldcup26:game:94":"760507"}',
        )
    )
    seen_event_ids: list[str] = []

    async def fake_summary(event_id):
        seen_event_ids.append(event_id)
        return {"boxscore": {"teams": []}}

    monkeypatch.setattr(provider, "_summary", fake_summary)

    try:
        healthy = await provider.healthcheck()
    finally:
        await provider.close()

    assert healthy is True
    assert seen_event_ids == ["760507"]
