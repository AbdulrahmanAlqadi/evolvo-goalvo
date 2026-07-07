from __future__ import annotations

from datetime import datetime, timedelta


def should_notify_change(
    previous: dict[str, float],
    current: dict[str, float],
    *,
    threshold: float,
    last_notified_at: datetime | None,
    now: datetime,
    cooldown_seconds: int,
) -> bool:
    if last_notified_at and now - last_notified_at < timedelta(seconds=cooldown_seconds):
        return False
    return (
        max(abs(current[key] - previous[key]) for key in ("home_win", "draw", "away_win"))
        >= threshold
    )
