# ADR 0003: SQLite local default with SQLAlchemy repositories

- Status: accepted
- Alternatives: PostgreSQL-only; in-memory state; SQLite behind repository abstractions.
- Decision: async SQLite is the no-infrastructure default; SQLAlchemy and Alembic preserve a PostgreSQL path.
- Rationale: required local startup and inspectable persistence.
- Tradeoffs: limited write concurrency and no distributed locking.
- Failure modes: lock contention under heavy polling. Bounded retries and single-process polling are required.
- Upgrade path: PostgreSQL plus durable queue for multi-worker production.
