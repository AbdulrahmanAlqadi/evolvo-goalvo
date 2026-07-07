from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from app.forecasting.elo import EloModel


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(logits)
    return exp / exp.sum(axis=1, keepdims=True)


def main() -> None:
    rows = list(
        csv.DictReader(Path("data/processed/historical_matches.csv").open(encoding="utf-8"))
    )
    rows.sort(key=lambda row: row["played_at"])
    elo = EloModel()
    x, y = [], []
    for row in rows:
        at = datetime.fromisoformat(row["played_at"].replace("Z", "+00:00"))
        diff = (
            elo.rating_at(row["home_team_id"], at) - elo.rating_at(row["away_team_id"], at)
        ) / 400
        neutral = 1.0 if row["neutral"].lower() == "true" else 0.0
        x.append([diff, neutral, 1.0])
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        y.append(0 if hg > ag else 1 if hg == ag else 2)
        elo.update(
            home_id=row["home_team_id"],
            away_id=row["away_team_id"],
            home_goals=hg,
            away_goals=ag,
            played_at=at,
            neutral=bool(neutral),
        )
    X = np.asarray(x, dtype=float)
    Y = np.eye(3)[np.asarray(y)]
    train_end = max(3, int(len(X) * 0.8))
    W = np.zeros((X.shape[1], 3))
    for _ in range(800):
        prediction = softmax(X[:train_end] @ W)
        gradient = X[:train_end].T @ (prediction - Y[:train_end]) / train_end + 1e-3 * W
        W -= 0.08 * gradient
    artifact = {
        "type": "multinomial_logistic_regression",
        "version": "demo-trained-v1",
        "feature_names": ["elo_diff_scaled", "neutral_venue", "bias"],
        "coefficients_feature_by_class": W.tolist(),
        "trained_matches": train_end,
        "trained_until": rows[train_end - 1]["played_at"],
        "warning": "Tiny included sample; not a production model.",
    }
    output = Path("data/models/prematch_classifier_demo.json")
    output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"artifact": str(output), "checksum": checksum}, indent=2))


if __name__ == "__main__":
    main()
