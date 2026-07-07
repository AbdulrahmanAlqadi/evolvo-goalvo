from __future__ import annotations

from dataclasses import dataclass

from app.domain.probabilities import OutcomeProbabilities, weighted_average


@dataclass(frozen=True, slots=True)
class ModelComponent:
    name: str
    probabilities: OutcomeProbabilities
    weight: float
    version: str


def combine_components(components: list[ModelComponent]) -> OutcomeProbabilities:
    return weighted_average((component.probabilities, component.weight) for component in components)
