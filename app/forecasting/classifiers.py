from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.domain.probabilities import OutcomeProbabilities


@dataclass(slots=True)
class TransparentMultinomialClassifier:
    """Small auditable softmax model.

    Coefficients are temporary demo defaults and are not presented as learned production weights.
    Training scripts can replace them with validation-derived JSON artifacts.
    """

    feature_names: tuple[str, ...] = (
        "elo_diff_scaled",
        "xg_diff",
        "neutral_venue",
        "data_completeness",
    )
    coefficients: list[list[float]] = field(
        default_factory=lambda: [
            [1.15, 0.90, -0.05, 0.10],
            [-0.05, -0.10, 0.10, 0.05],
            [-1.10, -0.80, -0.05, 0.10],
        ]
    )
    intercepts: list[float] = field(default_factory=lambda: [0.05, -0.15, 0.05])

    def predict(self, features: dict[str, float]) -> OutcomeProbabilities:
        vector = [float(features.get(name, 0.0)) for name in self.feature_names]
        logits = [
            intercept + sum(weight * value for weight, value in zip(row, vector, strict=True))
            for intercept, row in zip(self.intercepts, self.coefficients, strict=True)
        ]
        peak = max(logits)
        exps = [math.exp(value - peak) for value in logits]
        total = sum(exps)
        return OutcomeProbabilities(exps[0] / total, exps[1] / total, exps[2] / total).normalized()
