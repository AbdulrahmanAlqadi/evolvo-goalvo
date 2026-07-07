from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


def apply_temperature(values: list[float], temperature: float) -> list[float]:
    logits = [math.log(max(value, 1e-12)) / temperature for value in values]
    peak = max(logits)
    exp = [math.exp(value - peak) for value in logits]
    total = sum(exp)
    return [value / total for value in exp]


def main() -> None:
    source = Path("reports/backtest_predictions.csv")
    if not source.exists():
        raise SystemExit("Run python scripts/backtest.py first")
    rows = [
        row
        for row in csv.DictReader(source.open(encoding="utf-8"))
        if row["split"] == "validation" and row["model"] == "ensemble"
    ]
    if not rows:
        raise SystemExit("No validation predictions found")
    best = None
    for temperature in [0.6 + i * 0.05 for i in range(21)]:
        loss = 0.0
        for row in rows:
            values = apply_temperature(
                [float(row["home_win"]), float(row["draw"]), float(row["away_win"])], temperature
            )
            loss -= math.log(max(values[int(row["label"])], 1e-12))
        loss /= len(rows)
        if best is None or loss < best[1]:
            best = (temperature, loss)
    artifact = {
        "type": "temperature_scaling",
        "version": "demo-temperature-v1",
        "temperature": best[0],
        "validation_log_loss": best[1],
        "validation_count": len(rows),
        "warning": "Tiny validation sample; not production calibration.",
    }
    output = Path("data/models/calibration_demo.json")
    output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "artifact": str(output),
                "checksum": hashlib.sha256(output.read_bytes()).hexdigest(),
                **artifact,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
