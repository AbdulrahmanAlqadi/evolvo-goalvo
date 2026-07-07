# Arabic Football Forecast Agent

An offline-first FastAPI backend for Arabic football probability forecasts. It separates numerical forecasting from language generation: Elo, Poisson/Dixon–Coles, a transparent classifier and seeded live simulations produce the probabilities; an optional LLM may only explain a bounded evidence package.

## Scope and honesty

This repository is an executable engineering baseline, not a claim of predictive superiority. Replay mode works without paid APIs. The shipped team profiles and classifier coefficients are demo artifacts, not a production-trained World Cup model. `scripts/backtest.py` reports held-out metrics on the included tiny sample and labels them as non-representative. External providers require valid credentials and contract verification.

## Architecture

```text
football providers -> canonical domain models -> feature snapshots
                                           -> deterministic forecasting
                                           -> calibration -> strict response schema
                                           -> SQLite history / SSE / Telegram
                                           -> optional bounded Arabic LLM explanation
```

Key boundaries:

- Provider JSON is normalized inside `app/providers/football/`.
- Provider IDs never become canonical IDs implicitly.
- Features include event and availability timestamps; leakage checks reject future data.
- The LLM receives no authority to calculate or alter probabilities.
- Replay events are idempotent and VAR goal cancellations recompute canonical state.
- SQLite is the local default; SQLAlchemy repositories keep PostgreSQL migration possible.

## Implemented capabilities

- FastAPI `/api/v1` routes, health checks, API-key auth, process-local rate limiting, request IDs,
  strict schemas and SSE.
- World Cup-only serving mode that filters provider competitions before API, forecasting and
  Telegram surfaces can see non-World-Cup matches.
- Arabic national-team localization for user-facing names, while leaving provider IDs and numerical
  model inputs provider-neutral.
- WorldCup26, replay, mock, API-Football, football-data.org and TheSportsDB adapters.
- Tournament-form team-strength features from completed provider results, with leakage guards so
  future or unavailable matches cannot affect a forecast.
- Composite fallback provider with capability checks, cache, deduplication lock, rate budgets, bounded retry and circuit state.
- Elo, independent Poisson, Dixon–Coles correction, transparent softmax classifier and configurable ensemble.
- Seeded remaining-goals Monte Carlo updates with red-card and bounded xG effects.
- Regulation-versus-qualification logic for knockout matches, including extra-time and seeded
  shootout-state simulation without rewriting the settled 90-minute result.
- SQLite persistence, Alembic migration and prediction history.
- Deterministic Arabic explanation and Telegram formatting when every LLM is unavailable.
- Gemini three-slot concurrency-safe key pool and OpenAI-compatible fallback adapter.
- Telegram polling/webhook wiring, paginated Arabic menus, callback acknowledgement, allowed-user
  checks, duplicate-update protection, match actions and hashed subscription persistence.
- Replay, property, unit, integration and adversarial tests.

## Installation

Python 3.11+ is supported.

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -e ".[dev]"
```

Core and test dependencies are pinned to the versions exercised by the acceptance run. Optional LLM
and plotting extras remain separately installable because they were not credential-tested here.

Create configuration:

Windows:

```powershell
copy .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

The default `.env.example` is World Cup API-first:

```dotenv
WORLD_CUP_ONLY=true
TEAM_LOCALIZATION_PATH=./configs/team_localization_ar.json
FOOTBALL_PROVIDER=worldcup26
FOOTBALL_PROVIDER_FALLBACKS=api_football,football_data_org,thesportsdb,replay,mock
WORLDCUP26_BASE_URL=https://worldcup26.ir
```

For deterministic offline development, explicitly switch to:

```dotenv
FOOTBALL_PROVIDER=replay
FOOTBALL_PROVIDER_FALLBACKS=mock
REPLAY_MODE=true
LLM_ENABLED=false
```

Replay is only a local regression fixture. Production and Telegram evals should use `worldcup26`
or a credentialed provider and keep the World Cup competition IDs explicit in
`WORLD_CUP_COMPETITION_IDS`.

## Database and startup

```bash
alembic upgrade head
python scripts/run_demo.py
uvicorn app.main:app --reload
```

OpenAPI: `http://127.0.0.1:8000/docs`

Health:

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

Pre-match forecast:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/predictions/pre-match \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -d '{"match_id":"demo-match-001"}'
```

Live/replay refresh:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/predictions/demo-match-001/refresh \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -d '{"force":true}'
```

SSE:

```bash
curl -N -H "X-API-Key: change-me" http://127.0.0.1:8000/api/v1/predictions/demo-match-001/stream
```

## Telegram

Create a bot with BotFather, then set:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_MODE=polling
TELEGRAM_BOT_TOKEN=...
```

Development polling:

```bash
python -m app.bot
```

Webhook mode:

```dotenv
TELEGRAM_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://example.com/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=a-long-random-secret
```

Run FastAPI and register the webhook with Telegram using the same secret token. The endpoint rejects missing or mismatched `X-Telegram-Bot-Api-Secret-Token`.

## External football providers

### WorldCup26

Set `FOOTBALL_PROVIDER=worldcup26`. The adapter reads `/get/games` and `/get/teams`, maps provider
team IDs explicitly, localizes Arabic team labels, and serves only the FIFA World Cup competition
through the World Cup scope wrapper. It does not use any provider prediction endpoint as ground
truth; numerical probabilities still come from `app/forecasting/`. Completed scorelines from the
same feed are also replayed into deterministic goal events when scorer-minute data is present.

### Free team-strength priors

The app reads global team priors from `configs/team_profiles.json`. Refresh the file from the free
World Football Elo table with an explicit FIFA-code-to-Elo-code mapping:

```bash
python scripts/refresh_world_football_elo.py
```

The refresh writes Elo, attack and defence priors for the 48 currently mapped World Cup teams. The
runtime never joins on display names and never fetches this source inside a prediction request.

### API-Football

Set `FOOTBALL_PROVIDER=api_football`, `API_FOOTBALL_KEY`, competition/season and verified base URL. Coverage varies by league and season; inspect capability/coverage fields before enabling endpoints. The app does not use the provider prediction endpoint as ground truth.

### football-data.org

Set `FOOTBALL_PROVIDER=football_data_org` and `FOOTBALL_DATA_ORG_KEY`. The free plan is rate-limited, so it is not treated as high-frequency real-time coverage.

### TheSportsDB

The adapter is fixture-oriented and explicitly reports no live-event, injury, lineup or xG capability.
With `WORLD_CUP_ONLY=true`, generic TheSportsDB soccer fixtures that are not identified as FIFA
World Cup matches are filtered out.

Run a credentialed smoke test:

```bash
python scripts/provider_smoke_test.py
```

## LLM explanation layer

The API remains operational with `LLM_ENABLED=false`. For Gemini:

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=gemini
LLM_MODEL=your-current-supported-model
GEMINI_API_KEY_1=...
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
```

Install optional dependencies:

```bash
pip install -e ".[llm]"
```

The Gemini adapter uses the official `google-genai` SDK. Key slots enter cooldown on 429/transient failures, become permanently unhealthy on authentication failures, and are logged only by anonymous slot number.

## Tests

```bash
pytest
ruff check app tests scripts
```

The suite covers probability invariants, deterministic seeds, leakage, VAR rollback, duplicate events, key cooldown, API auth, provider outage, LLM fallback and Telegram formatting.

## Replay and evaluation

```bash
python scripts/replay_match.py --fixture data/replay/live_adversarial.json
python scripts/evaluate_real_worldcup_provider.py
python scripts/evaluate_prediction_signal.py
python scripts/evaluate_world_cup_scope.py
python scripts/evaluate_telegram_buttons.py
python scripts/evaluate_live_replay.py
python scripts/backtest.py
```

Outputs are written under `reports/`. The included dataset is intentionally small and only validates the evaluation pipeline; it is not evidence of production accuracy.

## Training and calibration

```bash
python scripts/train_models.py
python scripts/calibrate_models.py
```

Artifacts use JSON plus SHA-256 checksums. No unsafe pickle loading is used.
The manifest is `data/models/registry.json`; model cards are under `docs/model-card-*.md`.

## Data flow and failure behavior

- Provider unavailable: a supported fallback is attempted; otherwise a typed 503 is returned.
- Stale live data: the previous value is explicitly marked stale and notifications should be suppressed.
- Missing calibration: behavior is controlled by `ALLOW_UNCALIBRATED_FALLBACK`; production should fail closed.
- LLM unavailable or invalid: deterministic Arabic text is used without touching numbers.
- Database unavailable: readiness degrades and persistence is not reported as successful.
- Provider corrections: canonical state is rebuilt from event history; cancelled goals are removed.

## Security notes

- `.env` is ignored.
- API keys are compared in constant time where practical.
- Provider base hosts are allow-listed and HTTPS-only.
- Request sizes, HTTP timeouts, retries and response sizes are bounded.
- HTTP API and Telegram callback request rates are bounded in-process.
- Logs redact key/token/authorization patterns and do not include raw Telegram user IDs.
- Model artifacts are JSON with checksum verification; do not load untrusted joblib or pickle files.

## Known limitations

- Demo ratings and coefficients are illustrative and must be replaced by temporally trained artifacts.
- Team-strength signal uses World Football Elo priors, completed tournament results, opponent-adjusted
  form, rest days and a small fatigue adjustment when available. Player injuries, tactical/coaching
  feeds, market odds, xG and confirmed lineups remain explicit unavailable signals until a reliable
  free provider exists; the app must not fabricate them.
- The local replay fixture is synthetic and must not be treated as a production schedule.
- `worldcup26` is a free public fixture/live-score source; keep API-Football or another licensed
  provider configured as an optional production fallback when stronger data guarantees are needed.
- API-Football event identity may require provider-specific refinement after inspecting licensed payloads.
- football-data.org does not expose a uniform high-granularity event stream for this use case.
- Telegram subscription preferences are persisted using hashed user identifiers. The currently
  connected process retains the chat identifier needed for delivery; restart-safe delivery requires
  an encrypted contact mapping or an external queue and remains an upgrade item.
- API and Telegram rate limits are process-local and must be replaced by a shared atomic backend for
  multi-worker deployment.
- Multi-leg ties are an extension point, not implemented.
- The simple live model is a reproducible MVP, not a trained Bayesian event-hazard model.

See `docs/limitations.md`, `docs/research.md` and `docs/adrs/` for detail.
