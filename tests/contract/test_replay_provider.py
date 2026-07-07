from pathlib import Path

import pytest

from app.providers.football.replay import ReplayFootballProvider


@pytest.mark.asyncio
async def test_replay_provider_contract():
    provider = ReplayFootballProvider(Path("data/replay/sample_match.json"))
    matches = await provider.list_matches()
    assert len(matches) == 1
    match = await provider.get_match("demo-match-001")
    assert match.home_team.id == "arg"
    assert match.home_team.name_ar == "الأرجنتين"
    events = await provider.get_match_events(match.id)
    assert any(event.type.value == "GOAL_CANCELLED" for event in events)
    assert (await provider.get_provider_coverage()).live_events
