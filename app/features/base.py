from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, model_validator


class FeatureValue(BaseModel):
    name: str
    value: float | int | str | bool | None
    dtype: Literal["float", "int", "str", "bool"]
    source: str
    event_timestamp: datetime
    availability_timestamp: datetime
    missing_policy: str
    leakage_risk: str
    transformation: str = "identity"
    valid_min: float | None = None
    valid_max: float | None = None

    @model_validator(mode="after")
    def validate_availability_and_range(self) -> FeatureValue:
        if self.availability_timestamp < self.event_timestamp:
            raise ValueError("availability timestamp cannot precede the source event timestamp")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            if self.valid_min is not None and self.value < self.valid_min:
                raise ValueError(f"{self.name} is below its valid range")
            if self.valid_max is not None and self.value > self.valid_max:
                raise ValueError(f"{self.name} is above its valid range")
        return self


def assert_no_future_data(features: list[FeatureValue], prediction_time: datetime) -> None:
    future = [
        feature.name for feature in features if feature.availability_timestamp > prediction_time
    ]
    if future:
        raise ValueError(f"future-data leakage detected: {', '.join(future)}")


def feature_dict(features: list[FeatureValue]) -> dict[str, Any]:
    return {feature.name: feature.value for feature in features}
