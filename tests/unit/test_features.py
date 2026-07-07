from datetime import UTC, datetime, timedelta

import pytest

from app.features.base import FeatureValue, assert_no_future_data


def test_future_data_leakage_rejected():
    prediction_time = datetime(2026, 1, 1, tzinfo=UTC)
    feature = FeatureValue(
        name="lineup",
        value=1,
        dtype="int",
        source="provider",
        event_timestamp=prediction_time,
        availability_timestamp=prediction_time + timedelta(hours=1),
        missing_policy="missing",
        leakage_risk="critical",
    )
    with pytest.raises(ValueError, match="future-data leakage"):
        assert_no_future_data([feature], prediction_time)
