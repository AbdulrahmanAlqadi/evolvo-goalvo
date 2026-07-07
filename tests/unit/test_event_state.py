from datetime import UTC, datetime

from app.domain.entities import MatchEvent
from app.domain.enums import EventType, TeamSide
from app.domain.events import CanonicalMatchState


def event(event_id, event_type, side, related=None):
    now = datetime.now(UTC)
    return MatchEvent(
        id=event_id,
        match_id="m",
        provider="replay",
        provider_event_id=event_id,
        type=event_type,
        side=side,
        minute=10,
        occurred_at=now,
        received_at=now,
        related_event_id=related,
    )


def test_duplicate_event_is_idempotent():
    state = CanonicalMatchState()
    goal = event("g1", EventType.GOAL, TeamSide.HOME)
    assert state.apply(goal) is True
    assert state.apply(goal) is False
    assert state.score.home == 1


def test_cancelled_goal_is_removed():
    state = CanonicalMatchState()
    state.apply(event("g1", EventType.GOAL, TeamSide.AWAY))
    state.apply(event("c1", EventType.GOAL_CANCELLED, TeamSide.AWAY, related="g1"))
    assert state.score.away == 0
