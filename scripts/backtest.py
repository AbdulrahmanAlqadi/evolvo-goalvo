from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.domain.probabilities import OutcomeProbabilities
from app.forecasting.elo import EloModel
from app.forecasting.poisson import forecast_poisson


@dataclass
class Row:
    played_at: datetime
    competition: str
    stage: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    neutral: bool

    @property
    def label(self) -> int:
        return (
            0
            if self.home_goals > self.away_goals
            else 1
            if self.home_goals == self.away_goals
            else 2
        )


def load_rows(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as stream:
        items = [
            Row(
                played_at=datetime.fromisoformat(raw["played_at"].replace("Z", "+00:00")),
                competition=raw["competition"],
                stage=raw["stage"],
                home=raw["home_team_id"],
                away=raw["away_team_id"],
                home_goals=int(raw["home_goals"]),
                away_goals=int(raw["away_goals"]),
                neutral=raw["neutral"].lower() == "true",
            )
            for raw in csv.DictReader(stream)
        ]
    return sorted(items, key=lambda item: item.played_at)


def metrics(probabilities: list[OutcomeProbabilities], labels: list[int]) -> dict:
    if not labels:
        return {"count": 0}
    eps = 1e-15
    tuples = [p.as_tuple() for p in probabilities]
    log_loss = -sum(
        math.log(max(eps, values[label])) for values, label in zip(tuples, labels, strict=True)
    ) / len(labels)
    brier = sum(
        sum((values[i] - (1.0 if i == label else 0.0)) ** 2 for i in range(3))
        for values, label in zip(tuples, labels, strict=True)
    ) / len(labels)
    accuracy = sum(
        max(range(3), key=lambda i: values[i]) == label
        for values, label in zip(tuples, labels, strict=True)
    ) / len(labels)
    confidences = [max(values) for values in tuples]
    correct = [
        float(max(range(3), key=lambda i: values[i]) == label)
        for values, label in zip(tuples, labels, strict=True)
    ]
    ece = 0.0
    for low in [i / 5 for i in range(5)]:
        high = low + 0.2
        idx = [
            i
            for i, value in enumerate(confidences)
            if low <= value < high or (high == 1 and value == 1)
        ]
        if idx:
            ece += (
                len(idx)
                / len(labels)
                * abs(
                    sum(confidences[i] for i in idx) / len(idx)
                    - sum(correct[i] for i in idx) / len(idx)
                )
            )
    return {
        "count": len(labels),
        "log_loss": log_loss,
        "multiclass_brier": brier,
        "accuracy": accuracy,
        "ece_5_bin": ece,
    }


def bootstrap_ci(
    probabilities: list[OutcomeProbabilities],
    labels: list[int],
    repeats: int = 300,
    seed: int = 2026,
) -> dict:
    if not labels:
        return {}
    rng = random.Random(seed)
    values = []
    for _ in range(repeats):
        indices = [rng.randrange(len(labels)) for _ in labels]
        sample = metrics([probabilities[i] for i in indices], [labels[i] for i in indices])
        values.append(sample["log_loss"])
    values.sort()
    return {
        "log_loss_95pct": [
            values[int(0.025 * len(values))],
            values[min(len(values) - 1, int(0.975 * len(values)))],
        ]
    }


def run() -> dict:
    rows = load_rows(Path("data/processed/historical_matches.csv"))
    train_end = max(1, int(len(rows) * 0.60))
    validation_end = max(train_end + 1, int(len(rows) * 0.80))
    elo = EloModel()
    records: list[dict] = []
    for index, row in enumerate(rows):
        elo_p = elo.probabilities(row.home, row.away, row.played_at, row.neutral)
        rating_diff = elo.rating_at(row.home, row.played_at) - elo.rating_at(
            row.away, row.played_at
        )
        home_xg = max(0.35, min(3.5, 1.25 * 10 ** (rating_diff / 1200)))
        away_xg = max(0.35, min(3.5, 1.15 * 10 ** (-rating_diff / 1200)))
        poisson_p = forecast_poisson(home_xg, away_xg).probabilities
        ensemble = OutcomeProbabilities(
            0.45 * elo_p.home_win + 0.55 * poisson_p.home_win,
            0.45 * elo_p.draw + 0.55 * poisson_p.draw,
            0.45 * elo_p.away_win + 0.55 * poisson_p.away_win,
        ).normalized()
        split = "train" if index < train_end else "validation" if index < validation_end else "test"
        records.append(
            {
                "split": split,
                "played_at": row.played_at.isoformat(),
                "label": row.label,
                "elo": elo_p.as_tuple(),
                "poisson": poisson_p.as_tuple(),
                "ensemble": ensemble.as_tuple(),
                "stage": row.stage,
            }
        )
        elo.update(
            home_id=row.home,
            away_id=row.away,
            home_goals=row.home_goals,
            away_goals=row.away_goals,
            played_at=row.played_at,
            importance=1.5 if row.competition in {"WC", "EURO"} else 1.0,
            neutral=row.neutral,
        )

    test = [record for record in records if record["split"] == "test"]
    labels = [record["label"] for record in test]
    model_metrics = {}
    for name in ["elo", "poisson", "ensemble"]:
        probs = [OutcomeProbabilities(*record[name]) for record in test]
        model_metrics[name] = {**metrics(probs, labels), **bootstrap_ci(probs, labels)}
    naive = [OutcomeProbabilities(1 / 3, 1 / 3, 1 / 3) for _ in labels]
    model_metrics["naive_uniform"] = metrics(naive, labels)
    report = {
        "dataset_period": [rows[0].played_at.isoformat(), rows[-1].played_at.isoformat()],
        "matches": len(rows),
        "boundaries": {
            "train_end_index": train_end,
            "validation_end_index": validation_end,
            "test_count": len(test),
        },
        "feature_availability_assumptions": [
            "Only results strictly before each match update Elo",
            "No lineup, injury, market or post-match features are used",
        ],
        "models": model_metrics,
        "limitations": (
            "Tiny selective sample. Metrics validate the pipeline only and are not "
            "evidence of production accuracy."
        ),
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/backtest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with Path("reports/backtest_predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["split", "played_at", "label", "model", "home_win", "draw", "away_win", "stage"]
        )
        for record in records:
            for name in ["elo", "poisson", "ensemble"]:
                writer.writerow(
                    [
                        record["split"],
                        record["played_at"],
                        record["label"],
                        name,
                        *record[name],
                        record["stage"],
                    ]
                )
    try:
        import matplotlib.pyplot as plt

        ensemble_test = [OutcomeProbabilities(*record["ensemble"]) for record in test]
        confidence = [max(p.as_tuple()) for p in ensemble_test]
        correct = [
            int(max(range(3), key=lambda i: p.as_tuple()[i]) == label)
            for p, label in zip(ensemble_test, labels, strict=True)
        ]
        plt.figure()
        plt.scatter(confidence, correct)
        plt.xlabel("Forecast confidence")
        plt.ylabel("Correct top class")
        plt.title("Demo held-out reliability points")
        plt.savefig("reports/reliability_demo.png", bbox_inches="tight")
        plt.close()
    except ImportError:
        pass
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
