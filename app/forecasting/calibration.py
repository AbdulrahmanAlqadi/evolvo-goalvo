from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain.probabilities import OutcomeProbabilities


class CalibrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TemperatureCalibrator:
    temperature: float = 1.0
    version: str = "identity-v1"

    def apply(self, probabilities: OutcomeProbabilities) -> OutcomeProbabilities:
        if self.temperature <= 0 or not math.isfinite(self.temperature):
            raise CalibrationError("temperature must be finite and positive")
        p = probabilities.normalized()
        logits = [math.log(max(value, 1e-12)) / self.temperature for value in p.as_tuple()]
        peak = max(logits)
        exps = [math.exp(value - peak) for value in logits]
        total = sum(exps)
        return OutcomeProbabilities(*(value / total for value in exps)).normalized()
