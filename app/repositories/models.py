from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class CompetitionRow(Base, TimestampMixin):
    __tablename__ = "competitions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SeasonRow(Base, TimestampMixin):
    __tablename__ = "seasons"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamRow(Base, TimestampMixin):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)


class PlayerRow(Base, TimestampMixin):
    __tablename__ = "players"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CoachRow(Base, TimestampMixin):
    __tablename__ = "coaches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))


class VenueRow(Base, TimestampMixin):
    __tablename__ = "venues"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MatchRow(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("competition_id", "canonical_external_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), index=True)
    season_id: Mapped[str | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venues.id"), nullable=True)
    canonical_external_key: Mapped[str] = mapped_column(String(255))
    kickoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(64))
    neutral_venue: Mapped[bool] = mapped_column(Boolean, default=True)
    score_home: Mapped[int] = mapped_column(Integer, default=0)
    score_away: Mapped[int] = mapped_column(Integer, default=0)
    minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProviderMappingRow(Base, TimestampMixin):
    __tablename__ = "provider_mappings"
    __table_args__ = (UniqueConstraint("provider", "entity_type", "provider_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    provider_id: Mapped[str] = mapped_column(String(128))
    canonical_id: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)


class LineupRow(Base, TimestampMixin):
    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("match_id", "team_id", "player_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"))
    starter: Mapped[bool] = mapped_column(Boolean, default=False)
    formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    announced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerAvailabilityRow(Base, TimestampMixin):
    __tablename__ = "player_availability"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), index=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_confidence: Mapped[float] = mapped_column(Float, default=1.0)


class MatchEventRow(Base, TimestampMixin):
    __tablename__ = "match_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    provider_event_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(16))
    minute: Mapped[int] = mapped_column(Integer)
    second: Mapped[int] = mapped_column(Integer, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    related_event_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MatchStatisticsSnapshotRow(Base, TimestampMixin):
    __tablename__ = "match_statistics_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)


class PreMatchFeatureSnapshotRow(Base, TimestampMixin):
    __tablename__ = "pre_match_feature_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    feature_schema_version: Mapped[str] = mapped_column(String(64))


class LiveFeatureSnapshotRow(Base, TimestampMixin):
    __tablename__ = "live_feature_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    features_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    state_fingerprint: Mapped[str] = mapped_column(String(64), index=True)


class PredictionRow(Base, TimestampMixin):
    __tablename__ = "predictions"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(128))
    calibration_version: Mapped[str] = mapped_column(String(128))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)


class ProbabilityRevisionRow(Base, TimestampMixin):
    __tablename__ = "probability_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id"), index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_win: Mapped[float] = mapped_column(Float)
    draw: Mapped[float] = mapped_column(Float)
    away_win: Mapped[float] = mapped_column(Float)
    trigger_code: Mapped[str] = mapped_column(String(64))


class ModelVersionRow(Base, TimestampMixin):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    model_type: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(128))
    trained_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class CalibrationVersionRow(Base, TimestampMixin):
    __tablename__ = "calibration_versions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    method: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(128))


class DataQualityWarningRow(Base, TimestampMixin):
    __tablename__ = "data_quality_warnings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.id"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(96), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderRequestMetadataRow(Base, TimestampMixin):
    __tablename__ = "provider_request_metadata"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(96), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))


class TelegramSubscriptionRow(Base, TimestampMixin):
    __tablename__ = "telegram_subscriptions"
    __table_args__ = (UniqueConstraint("user_hash", "match_id", "kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_hash: Mapped[str] = mapped_column(String(128), index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    threshold: Mapped[float] = mapped_column(Float, default=0.08)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TelegramUserRow(Base, TimestampMixin):
    __tablename__ = "telegram_users"

    user_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    interaction_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditRecordRow(Base):
    __tablename__ = "audit_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(96), index=True)
    actor_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
