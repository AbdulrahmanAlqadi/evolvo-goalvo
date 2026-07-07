from __future__ import annotations

from datetime import datetime

from app.features.base import FeatureValue, assert_no_future_data


def build_lineup_features(lineups: list[dict], prediction_time: datetime) -> list[FeatureValue]:
    confirmed = [row for row in lineups if row.get("confirmed") is True]
    timestamps = [
        datetime.fromisoformat(row["announced_at"]) for row in confirmed if row.get("announced_at")
    ]
    observed = max(timestamps, default=prediction_time)
    features = [
        FeatureValue(
            name="confirmed_lineup_count",
            value=len(confirmed),
            dtype="int",
            source="lineup_provider",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="zero",
            leakage_risk="critical",
            valid_min=0,
            valid_max=22,
        )
    ]
    assert_no_future_data(features, prediction_time)
    return features
