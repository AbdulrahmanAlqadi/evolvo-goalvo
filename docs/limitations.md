# Limitations

- No supplied paid-provider credentials were available, so external HTTP integrations are implemented but not claimed as successfully exercised.
- The included historical sample is too small and selective for accuracy claims.
- Team strength profiles and classifier coefficients are demo inputs.
- The live fixture is synthetic and tests mechanics, correction handling and invariants rather than real provider fidelity.
- Player impact, travel, coach continuity, set pieces and market priors have schema/feature extension points but are not inferred when data is absent.
- Penalty-shootout strength is a symmetric baseline until validated player/team shootout data exists.
- Multi-leg ties are not implemented.
- Telegram subscription preferences are persisted with hashed user identifiers. The running process
  keeps the chat identifier for delivery, but restart-safe delivery needs encrypted contact mapping or
  a durable queue and is not included.
- SQLite is suitable for local operation, not a high-write multi-worker live deployment.
- API rate limiting is process-local. A multi-worker production deployment requires a shared,
  atomic limiter rather than multiplying the configured allowance per worker.
