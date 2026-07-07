from __future__ import annotations

from datetime import datetime

from app.domain.entities import Match
from app.features.base import FeatureValue


def build_context_features(match: Match, prediction_time: datetime) -> list[FeatureValue]:
    observed = min(match.updated_at, prediction_time)
    return [
        FeatureValue(
            name="is_knockout",
            value=match.is_knockout,
            dtype="bool",
            source="competition_rules",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="required",
            leakage_risk="low",
        ),
        FeatureValue(
            name="neutral_venue",
            value=match.neutral_venue,
            dtype="bool",
            source="fixture",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="true",
            leakage_risk="low",
        ),
    ]
