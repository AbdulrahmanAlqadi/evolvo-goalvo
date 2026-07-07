from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.domain.probabilities import OutcomeProbabilities


@dataclass(frozen=True, slots=True)
class LiveSimulationInput:
    minute: int
    home_score: int
    away_score: int
    prematch_home_xg: float
    prematch_away_xg: float
    red_cards_home: int = 0
    red_cards_away: int = 0
    observed_xg_home: float | None = None
    observed_xg_away: float | None = None
    regulation_minutes: int = 90


@dataclass(frozen=True, slots=True)
class LiveSimulationResult:
    probabilities: OutcomeProbabilities
    expected_remaining_home_goals: float
    expected_remaining_away_goals: float
    simulations: int
    seed: int


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def simulate_live(
    state: LiveSimulationInput,
    *,
    simulation_count: int,
    seed: int,
    min_multiplier: float = 0.25,
    max_multiplier: float = 2.5,
    red_card_effect: float = 0.78,
    xg_blend: float = 0.35,
) -> LiveSimulationResult:
    if simulation_count <= 0:
        raise ValueError("simulation_count must be positive")
    if not 0 <= state.minute <= 150:
        raise ValueError("minute is outside supported range")
    remaining_fraction = (
        max(0.0, state.regulation_minutes - state.minute) / state.regulation_minutes
    )
    home_intensity = state.prematch_home_xg * remaining_fraction
    away_intensity = state.prematch_away_xg * remaining_fraction

    card_delta = state.red_cards_away - state.red_cards_home
    home_intensity *= red_card_effect ** (-card_delta)
    away_intensity *= red_card_effect**card_delta

    elapsed_fraction = max(state.minute, 1) / state.regulation_minutes
    if state.observed_xg_home is not None:
        observed_rate = state.observed_xg_home / elapsed_fraction
        home_intensity = (
            1 - xg_blend
        ) * home_intensity + xg_blend * observed_rate * remaining_fraction
    if state.observed_xg_away is not None:
        observed_rate = state.observed_xg_away / elapsed_fraction
        away_intensity = (
            1 - xg_blend
        ) * away_intensity + xg_blend * observed_rate * remaining_fraction

    baseline_home = max(1e-9, state.prematch_home_xg * remaining_fraction)
    baseline_away = max(1e-9, state.prematch_away_xg * remaining_fraction)
    home_intensity = baseline_home * _bounded(
        home_intensity / baseline_home, min_multiplier, max_multiplier
    )
    away_intensity = baseline_away * _bounded(
        away_intensity / baseline_away, min_multiplier, max_multiplier
    )

    rng = np.random.default_rng(seed)
    home_final = state.home_score + rng.poisson(max(0.0, home_intensity), simulation_count)
    away_final = state.away_score + rng.poisson(max(0.0, away_intensity), simulation_count)
    home = float(np.mean(home_final > away_final))
    draw = float(np.mean(home_final == away_final))
    away = float(np.mean(home_final < away_final))
    return LiveSimulationResult(
        OutcomeProbabilities(home, draw, away).normalized(),
        home_intensity,
        away_intensity,
        simulation_count,
        seed,
    )


@dataclass(frozen=True, slots=True)
class ShootoutSimulationResult:
    home_advance: float
    away_advance: float
    simulations: int
    seed: int


def simulate_penalty_shootout(
    *,
    home_scored: int,
    away_scored: int,
    home_taken: int,
    away_taken: int,
    simulation_count: int,
    seed: int,
    home_score_probability: float = 0.75,
    away_score_probability: float = 0.75,
) -> ShootoutSimulationResult:
    if min(home_scored, away_scored, home_taken, away_taken) < 0:
        raise ValueError("shootout state cannot be negative")
    if not 0.0 <= home_score_probability <= 1.0:
        raise ValueError("home shootout probability must be within [0, 1]")
    if not 0.0 <= away_score_probability <= 1.0:
        raise ValueError("away shootout probability must be within [0, 1]")
    rng = np.random.default_rng(seed)
    home_wins = 0
    for _ in range(simulation_count):
        hs, aws = home_scored, away_scored
        ht, at = home_taken, away_taken
        while ht < 5 or at < 5:
            if ht <= at and ht < 5:
                hs += int(rng.random() < home_score_probability)
                ht += 1
            elif at < 5:
                aws += int(rng.random() < away_score_probability)
                at += 1
            home_remaining = max(0, 5 - ht)
            away_remaining = max(0, 5 - at)
            if hs > aws + away_remaining or aws > hs + home_remaining:
                break
        if hs == aws:
            for _pair in range(20):
                hs += int(rng.random() < home_score_probability)
                aws += int(rng.random() < away_score_probability)
                if hs != aws:
                    break
        if hs == aws:
            hs += int(rng.random() < 0.5)
        home_wins += int(hs > aws)
    home_probability = home_wins / simulation_count
    return ShootoutSimulationResult(
        home_advance=home_probability,
        away_advance=1.0 - home_probability,
        simulations=simulation_count,
        seed=seed,
    )
