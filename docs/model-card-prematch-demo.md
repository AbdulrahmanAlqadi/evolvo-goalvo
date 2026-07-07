# Model Card: Demo Pre-match Classifier and Calibration

## Intended use

Local demonstration, contract testing, replay testing, and validation of the forecasting pipeline. The artifact shows how a versioned classifier and a separately versioned calibration artifact are produced and checksum-verified.

## Non-intended use

It is not suitable for public predictions, betting, player evaluation, or claims of World Cup forecasting quality. The bundled historical sample is deliberately small and selective.

## Training data and period

- Source: `data/processed/historical_matches.csv`
- Training and validation observations: 20 included international matches
- Latest training timestamp: 2024-10-15 UTC
- Temporal split: earlier matches train the classifier; later matches are reserved for validation and testing

## Target and features

Target: home win, draw, or away win after regulation time. Demonstration features are a scaled Elo difference, neutral-venue indicator, and intercept. The runtime ensemble also contains Elo and Dixon–Coles-adjusted Poisson components.

## Validation

Run `python scripts/backtest.py` and `python scripts/calibrate_models.py`. Reports are written under `reports/`. Log loss, multiclass Brier score, accuracy, ECE, and bootstrap intervals are reported where the tiny sample permits calculation.

## Calibration

Temperature scaling is fit only on the validation partition. The held-out test partition is not used to fit the temperature.

## Missing data

Missing advanced features do not get fabricated. The runtime falls back to transparent team profiles and emits data-quality warnings.

## Known biases and limitations

The sample over-represents a few international teams and eras, has no validated lineup, injury, travel, or event-level xG history, and is far too small for stable coefficients. Results are mechanics demonstrations only.

## Version and reproduction

- Classifier: `demo-trained-v1`
- Calibration: `demo-temperature-v1`
- Reproduce: `python scripts/train_models.py && python scripts/calibrate_models.py`
- Integrity: checksums are recorded in `data/models/registry.json`
