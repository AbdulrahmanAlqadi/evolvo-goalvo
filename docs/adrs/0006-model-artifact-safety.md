# ADR 0006: JSON/checksummed model artifacts

- Status: accepted
- Alternatives: pickle/joblib; JSON; ONNX/skops.
- Decision: shipped artifacts are JSON with SHA-256 checksums. Unsafe pickle is prohibited.
- Rationale: inspectability and reduced arbitrary-code-execution risk.
- Tradeoffs: limited model classes in the baseline.
- Failure modes: artifact replacement or corruption. Registry loading fails on checksum mismatch.
- Upgrade path: signed ONNX/skops artifacts with explicit trust policy.
