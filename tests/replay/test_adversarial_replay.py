from pathlib import Path

import pytest

from app.domain.events import CanonicalMatchState
from app.providers.football.replay import ReplayFootballProvider


@pytest.mark.asyncio
async def test_adversarial_replay_history_is_consistent():
    provider = ReplayFootballProvider(Path("data/replay/live_adversarial.json"))
    events = await provider.get_match_events("demo-match-001")
    state = CanonicalMatchState()
    scores = []
    for event in events:
        state.apply(event)
        scores.append((state.score.home, state.score.away))
    assert scores[3] == (1, 2)
    assert scores[4] == (1, 1)
    assert scores[6] == (2, 1)
    assert state.shootout_home_taken == 1
    assert state.shootout_home_scored == 1
    assert state.shootout_away_taken == 0
