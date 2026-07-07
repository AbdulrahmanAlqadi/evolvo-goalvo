from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities import MatchEvent, Score
from app.domain.enums import EventType, TeamSide


@dataclass(slots=True)
class CanonicalMatchState:
    score: Score = field(default_factory=Score)
    red_cards_home: int = 0
    red_cards_away: int = 0
    applied_event_ids: set[str] = field(default_factory=set)
    goals_by_event_id: dict[str, TeamSide] = field(default_factory=dict)
    shootout_home_scored: int = 0
    shootout_away_scored: int = 0
    shootout_home_taken: int = 0
    shootout_away_taken: int = 0

    def apply(self, event: MatchEvent) -> bool:
        if event.id in self.applied_event_ids:
            return False
        self.applied_event_ids.add(event.id)

        if event.type in {EventType.GOAL, EventType.OWN_GOAL, EventType.PENALTY_SCORED}:
            if event.side == TeamSide.HOME:
                self.score.home += 1
            elif event.side == TeamSide.AWAY:
                self.score.away += 1
            self.goals_by_event_id[event.id] = event.side
        elif event.type == EventType.GOAL_CANCELLED:
            target = event.related_event_id
            side = self.goals_by_event_id.pop(target or "", None)
            if side == TeamSide.HOME:
                self.score.home = max(0, self.score.home - 1)
            elif side == TeamSide.AWAY:
                self.score.away = max(0, self.score.away - 1)
        elif event.type == EventType.SHOOTOUT_KICK:
            scored = bool(event.payload.get("scored", False))
            if event.side == TeamSide.HOME:
                self.shootout_home_taken += 1
                if scored:
                    self.shootout_home_scored += 1
            elif event.side == TeamSide.AWAY:
                self.shootout_away_taken += 1
                if scored:
                    self.shootout_away_scored += 1
        elif event.type in {EventType.RED_CARD, EventType.YELLOW_RED}:
            if event.side == TeamSide.HOME:
                self.red_cards_home += 1
            elif event.side == TeamSide.AWAY:
                self.red_cards_away += 1
        return True
