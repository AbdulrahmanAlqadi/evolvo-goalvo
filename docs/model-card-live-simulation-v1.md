# Model Card: Live Remaining-goals Simulation v1

## Intended use

Reproducible live probability updates during replay and development. It starts from pre-match expected goals and simulates remaining goals using the current score, elapsed time, bounded red-card effects, and xG snapshots when available.

## Non-intended use

It is not a trained event-level production model and must not be described as real-time when the upstream provider is stale or quota-limited. It is not a betting system.

## Training data

No fitted event-level artifact is shipped. Parameters are transparent configuration defaults and therefore require competition-specific validation before production use.

## Inputs

Current score, minute, pre-match expected goals, red-card counts, optional observed xG, regulation phase, simulation count, and seed. Shootout simulation consumes only the canonical kick state and bounded scoring probabilities.

## Validation

Property and replay tests enforce finite normalized probabilities, deterministic output for the same seed, no negative intensities, VAR rollback, phase semantics, and idempotent event application. Run `pytest` and `python scripts/evaluate_live_replay.py`.

## Missing data behaviour

When live xG is absent, the model uses the pre-match scoring prior and marks the missing statistics. Stale data is explicitly flagged and notification logic suppresses stale changes.

## Known limitations

Red-card and xG effects are bounded heuristics, penalty strength is symmetric by default, stoppage time is simplified, and the model has not been fit on a large licensed event stream.

## Version and reproduction

- Version: `live-simulation-v1`
- Reproduce replay: `python scripts/replay_match.py --fixture data/replay/live_adversarial.json`
- Randomness: NumPy generator with an explicit seed recorded in every prediction
