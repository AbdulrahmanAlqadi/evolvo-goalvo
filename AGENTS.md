# Repository instructions for coding agents

## Non-negotiable invariants

1. Numerical probabilities are produced only by deterministic or seeded forecasting code under `app/forecasting/`.
2. LLM code may explain structured evidence; it must never mutate `Outcome90`, `Qualification` or model inputs.
3. Every probability must be finite, within `[0,1]` and normalized within `1e-8`.
4. Do not conflate the 90-minute result with knockout qualification.
5. Historical features must satisfy `availability_timestamp <= prediction_time`.
6. Provider JSON must not leak beyond provider adapters.
7. Provider IDs require explicit canonical mappings; never join solely on display name.
8. Event ingestion must remain idempotent, correction-aware and order-replayable. Once extra time
   begins, `outcomes_90_minutes` represents the settled regulation result; only qualification may move.
9. No secrets, raw authorization headers, full Telegram update payloads or raw user IDs in logs.
10. Replay mode and numerical prediction must work when all external providers and LLMs are unavailable.

## Commands

```bash
pip install -e ".[dev]"
alembic upgrade head
pytest
ruff check app tests scripts
python scripts/run_demo.py
python scripts/replay_match.py --fixture data/replay/live_adversarial.json
python scripts/backtest.py
uvicorn app.main:app --reload
```

## Architectural boundaries

- `app/domain`: provider-neutral entities and invariants.
- `app/providers`: all external SDK/HTTP translation and retry semantics.
- `app/features`: timestamped, leakage-auditable feature construction.
- `app/forecasting`: pure numerical methods with no HTTP, DB or LLM dependency.
- `app/services`: orchestration, persistence and explanation fallback.
- `app/api`: transport only; do not put model logic in routes.
- `app/telegram`: presentation and callbacks only.

## Required tests for changes

- Forecast math: unit plus property/invariant tests.
- Provider change: stored-fixture contract test and malformed-input test.
- Feature change: availability timestamp and leakage regression tests.
- Live-event change: duplicate, out-of-order and correction replay tests.
- LLM change: outage fallback and attempted numeric alteration test.
- Security change: secret-redaction and unauthenticated access tests.

## Prohibited shortcuts

No random percentages, winner hardcoding, provider prediction passthrough, random time-series split, unbounded retries, unsafe pickle, dynamic `eval`, fabricated xG/injury data, silent stale data or `pass` in mandatory production paths.
