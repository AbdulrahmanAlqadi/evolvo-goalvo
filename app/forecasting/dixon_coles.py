from __future__ import annotations


def tau(home_goals: int, away_goals: int, home_xg: float, away_xg: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - home_xg * away_xg * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + home_xg * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + away_xg * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def apply_dixon_coles(
    matrix: list[list[float]], home_xg: float, away_xg: float, rho: float
) -> list[list[float]]:
    corrected = [row[:] for row in matrix]
    for home in range(min(2, len(corrected))):
        for away in range(min(2, len(corrected[home]))):
            corrected[home][away] *= max(0.0, tau(home, away, home_xg, away_xg, rho))
    total = sum(sum(row) for row in corrected)
    if total <= 0:
        raise ValueError("Dixon-Coles correction produced invalid matrix")
    return [[value / total for value in row] for row in corrected]
