# ADR 0002: Provider-neutral canonical domain

- Status: accepted
- Alternatives: provider JSON throughout the app; one provider-specific service; canonical domain adapters.
- Decision: every adapter maps to typed competition, team, match, event and statistics models.
- Rationale: provider replacement, conflict handling and testable replay.
- Tradeoffs: mapping work and incomplete common denominator.
- Failure modes: uncertain entity mappings. They are rejected/logged rather than joined by display name.
- Upgrade path: reviewed alias UI and confidence-scored multi-provider entity resolution.
