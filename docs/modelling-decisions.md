# Modelling decisions

## Baselines

- **Elo**: compact opponent-adjusted strength and inactivity regression.
- **Poisson**: interpretable expected goals and complete scoreline matrix.
- **Dixon–Coles**: configurable low-score adjustment; disabled/reweighted if validation rejects it.
- **Transparent classifier**: softmax over auditable features; demo coefficients are explicitly temporary.

## Ensemble

Weights are configurable. Shipped values are temporary demo defaults, not claims of validation-optimality. `scripts/train_models.py` and temporal evaluation are the path to replacement. Missing components are removed and remaining weights normalized.

## Calibration

Calibration is a separate stage. The shipped identity temperature (`1.0`) preserves baseline probabilities. Production artifacts must be fitted only on validation periods, checksummed and never fitted on the test period.

## Live model

The model begins with pre-match expected goals, scales by time remaining, applies bounded red-card effects and optionally blends observed xG. Seeded Poisson simulations produce reproducible final-score samples. This is simpler and more defensible than pretending to have a trained event-hazard model without the data.

## Knockout

The 90-minute draw probability feeds extra-time and penalty branches. Qualification sums to one and is never represented as a three-class draw outcome.
