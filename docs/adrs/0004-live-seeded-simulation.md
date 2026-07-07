# ADR 0004: Seeded remaining-goals simulation for live MVP

- Status: accepted
- Alternatives: ad-hoc probability shifts; trained survival model; Bayesian event process; seeded Poisson simulation.
- Decision: start from pre-match xG, scale remaining intensity by time, bounded cards and optional observed xG, then simulate reproducibly.
- Rationale: defensible without pretending event-level training data exists.
- Tradeoffs: simplified tactical dynamics and late-game behavior.
- Failure modes: extreme provider statistics. Inputs and multipliers are bounded.
- Upgrade path: calibrated hazard/Bayesian model behind the same interface.
