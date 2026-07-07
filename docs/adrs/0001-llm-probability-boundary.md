# ADR 0001: LLM excluded from probability generation

- Status: accepted
- Alternatives: LLM-only forecast; LLM-adjusted statistical forecast; deterministic forecast with LLM explanation.
- Decision: numerical output is produced only by deterministic/seeded forecasting components. The LLM receives bounded evidence and returns text-only schema.
- Rationale: reproducibility, testability, calibration and hallucination containment.
- Tradeoffs: explanations may be less flexible; numerical model work cannot be delegated to a general model.
- Failure modes: LLM adds unsupported facts or numbers. Validation rejects the output and deterministic Arabic templates take over.
- Upgrade path: richer evidence-grounded generation with citation IDs, still outside the numerical path.
