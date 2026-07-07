from __future__ import annotations

from datetime import datetime

from app.features.base import FeatureValue


def build_data_quality_features(
    *, prediction_time: datetime, available_groups: set[str], expected_groups: set[str]
) -> list[FeatureValue]:
    completeness = len(available_groups & expected_groups) / max(1, len(expected_groups))
    return [
        FeatureValue(
            name="data_completeness",
            value=completeness,
            dtype="float",
            source="data_quality",
            event_timestamp=prediction_time,
            availability_timestamp=prediction_time,
            missing_policy="required",
            leakage_risk="low",
            valid_min=0,
            valid_max=1,
        )
    ]
