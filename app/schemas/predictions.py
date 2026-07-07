from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompetitionRef(BaseModel):
    id: str
    name: str
    name_ar: str | None = None
    season: str


class TeamRef(BaseModel):
    id: str
    name: str
    name_ar: str | None = None


class Outcome90(BaseModel):
    home_win: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, le=1)
    away_win: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def sums_to_one(self) -> Outcome90:
        if abs(self.home_win + self.draw + self.away_win - 1.0) > 1e-8:
            raise ValueError("90-minute probabilities must sum to one")
        return self


class Qualification(BaseModel):
    home_advance: float = Field(ge=0, le=1)
    away_advance: float = Field(ge=0, le=1)
    extra_time: float = Field(ge=0, le=1)
    penalties: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def sums_to_one(self) -> Qualification:
        if abs(self.home_advance + self.away_advance - 1.0) > 1e-8:
            raise ValueError("qualification probabilities must sum to one")
        return self


class ExpectedGoals(BaseModel):
    home: float = Field(ge=0, le=15)
    away: float = Field(ge=0, le=15)
    remaining_home: float | None = Field(default=None, ge=0, le=15)
    remaining_away: float | None = Field(default=None, ge=0, le=15)


class Scoreline(BaseModel):
    home_goals: int = Field(ge=0, le=20)
    away_goals: int = Field(ge=0, le=20)
    probability: float = Field(ge=0, le=1)


class Uncertainty(BaseModel):
    level: Literal["low", "medium", "high"]
    reason_codes: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    code: str
    direction: Literal["HOME", "AWAY", "DRAW", "NEUTRAL"]
    importance: float = Field(ge=0, le=1)
    description_ar: str


class DataQuality(BaseModel):
    completeness: float = Field(ge=0, le=1)
    freshness_seconds: int = Field(ge=0)
    cached: bool = False
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)


class ModelMetadata(BaseModel):
    ensemble_version: str
    calibration_version: str
    component_versions: dict[str, str]
    simulation_count: int | None = None
    simulation_seed: int | None = None


class Explanation(BaseModel):
    headline_ar: str
    summary_ar: str
    key_factors_ar: list[str]
    uncertainty_ar: str
    data_warning_ar: str | None = None
    generated_by: Literal["deterministic", "llm"] = "deterministic"


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: str
    match_id: str
    competition: CompetitionRef
    home_team: TeamRef
    away_team: TeamRef
    status: str
    generated_at: datetime
    data_as_of: datetime
    data_freshness_seconds: int = Field(ge=0)
    outcomes_90_minutes: Outcome90
    qualification: Qualification | None = None
    expected_goals: ExpectedGoals
    likely_scorelines: list[Scoreline]
    uncertainty: Uncertainty
    evidence: list[EvidenceItem]
    data_quality: DataQuality
    model: ModelMetadata
    provenance: list[dict]
    explanation: Explanation
    movement_since_previous: dict[str, float] | None = None
    disclaimer_ar: str

    @model_validator(mode="after")
    def enforce_knockout_contract(self) -> PredictionResponse:
        knockout_stages = {
            "ROUND_OF_32",
            "ROUND_OF_16",
            "QUARTER_FINAL",
            "SEMI_FINAL",
            "THIRD_PLACE",
            "FINAL",
        }
        if self.competition and self.status == "FINISHED" and self.data_quality.stale:
            raise ValueError("finished matches cannot remain stale-live predictions")
        if self.qualification is None and any(
            item.get("stage") in knockout_stages
            for item in self.provenance
            if isinstance(item, dict)
        ):
            raise ValueError("knockout prediction requires qualification probabilities")
        return self


class PreMatchPredictionRequest(BaseModel):
    match_id: str
    generated_at: datetime | None = None


class RefreshPredictionRequest(BaseModel):
    force: bool = False
