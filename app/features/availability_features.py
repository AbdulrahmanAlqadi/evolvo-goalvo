from __future__ import annotations

from datetime import datetime

from app.features.base import FeatureValue, assert_no_future_data


def build_availability_features(
    records: list[dict], prediction_time: datetime
) -> list[FeatureValue]:
    eligible = [
        row for row in records if datetime.fromisoformat(row["available_at"]) <= prediction_time
    ]
    unavailable = sum(row.get("status") in {"OUT", "SUSPENDED"} for row in eligible)
    observed = max(
        (datetime.fromisoformat(row["available_at"]) for row in eligible), default=prediction_time
    )
    features = [
        FeatureValue(
            name="unavailable_players",
            value=unavailable,
            dtype="int",
            source="availability_provider",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="missing_indicator",
            leakage_risk="critical",
            valid_min=0,
            valid_max=50,
        )
    ]
    assert_no_future_data(features, prediction_time)
    return features
