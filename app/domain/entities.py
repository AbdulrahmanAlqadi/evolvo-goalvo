from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import EventType, MatchStage, MatchStatus, TeamSide


class ProviderCapabilities(BaseModel):
    fixtures: bool = False
    live_events: bool = False
    lineups: bool = False
    injuries: bool = False
    statistics: bool = False
    expected_goals: bool = False
    odds: bool = False
    standings: bool = False
    squads: bool = False


class Provenance(BaseModel):
    provider: str
    provider_entity_id: str | None = None
    field: str | None = None
    observed_at: datetime
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Team(BaseModel):
    id: str
    name: str
    name_ar: str | None = None
    country_code: str | None = None
    provider_ids: dict[str, str] = Field(default_factory=dict)


class Competition(BaseModel):
    id: str
    name: str
    name_ar: str | None = None
    season: str
    provider_ids: dict[str, str] = Field(default_factory=dict)


class Score(BaseModel):
    home: int = Field(default=0, ge=0)
    away: int = Field(default=0, ge=0)
    home_penalties: int | None = Field(default=None, ge=0)
    away_penalties: int | None = Field(default=None, ge=0)


class Match(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    competition: Competition
    home_team: Team
    away_team: Team
    kickoff: datetime
    status: MatchStatus
    stage: MatchStage = MatchStage.OTHER
    neutral_venue: bool = True
    host_team_id: str | None = None
    venue: str | None = None
    minute: int | None = Field(default=None, ge=0, le=150)
    period: str | None = None
    score: Score = Field(default_factory=Score)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provenance: list[Provenance] = Field(default_factory=list)

    @property
    def is_knockout(self) -> bool:
        return self.stage not in {MatchStage.GROUP, MatchStage.OTHER}


class MatchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    match_id: str
    provider: str
    provider_event_id: str
    type: EventType
    side: TeamSide
    minute: int = Field(ge=0, le=150)
    second: int = Field(default=0, ge=0, le=59)
    player_id: str | None = None
    related_event_id: str | None = None
    is_cancelled: bool = False
    occurred_at: datetime
    received_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class MatchStatistics(BaseModel):
    match_id: str
    captured_at: datetime
    possession_home: float | None = Field(default=None, ge=0, le=100)
    possession_away: float | None = Field(default=None, ge=0, le=100)
    shots_home: int | None = Field(default=None, ge=0)
    shots_away: int | None = Field(default=None, ge=0)
    shots_on_target_home: int | None = Field(default=None, ge=0)
    shots_on_target_away: int | None = Field(default=None, ge=0)
    xg_home: float | None = Field(default=None, ge=0)
    xg_away: float | None = Field(default=None, ge=0)
    corners_home: int | None = Field(default=None, ge=0)
    corners_away: int | None = Field(default=None, ge=0)
    red_cards_home: int = Field(default=0, ge=0, le=5)
    red_cards_away: int = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def validate_possession(self) -> MatchStatistics:
        if self.possession_home is not None and self.possession_away is not None:
            if abs(self.possession_home + self.possession_away - 100.0) > 2.0:
                raise ValueError("possession values must sum to approximately 100")
        return self
