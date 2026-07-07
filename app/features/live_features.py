from __future__ import annotations

from datetime import datetime

from app.domain.entities import Match, MatchStatistics
from app.features.base import FeatureValue, assert_no_future_data


def build_live_features(
    match: Match, statistics: MatchStatistics | None, prediction_time: datetime
) -> list[FeatureValue]:
    observed = min(match.updated_at, prediction_time)
    minute = match.minute or 0
    values = [
        FeatureValue(
            name="minute",
            value=minute,
            dtype="int",
            source="match_state",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="zero",
            leakage_risk="low",
            valid_min=0,
            valid_max=150,
        ),
        FeatureValue(
            name="score_diff",
            value=match.score.home - match.score.away,
            dtype="int",
            source="match_state",
            event_timestamp=observed,
            availability_timestamp=observed,
            missing_policy="required",
            leakage_risk="low",
            valid_min=-20,
            valid_max=20,
        ),
    ]
    if statistics:
        for name, value, minimum, maximum in [
            ("xg_home", statistics.xg_home, 0, 15),
            ("xg_away", statistics.xg_away, 0, 15),
            ("shots_home", statistics.shots_home, 0, 100),
            ("shots_away", statistics.shots_away, 0, 100),
            ("red_cards_home", statistics.red_cards_home, 0, 5),
            ("red_cards_away", statistics.red_cards_away, 0, 5),
        ]:
            values.append(
                FeatureValue(
                    name=name,
                    value=value,
                    dtype="float" if "xg" in name else "int",
                    source="provider_statistics",
                    event_timestamp=statistics.captured_at,
                    availability_timestamp=statistics.captured_at,
                    missing_policy="ignore",
                    leakage_risk="high",
                    valid_min=minimum,
                    valid_max=maximum,
                )
            )
    assert_no_future_data(values, prediction_time)
    return values
