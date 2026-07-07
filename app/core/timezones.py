from __future__ import annotations

from datetime import timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_FIXED_ZONE_OFFSETS = {
    "Asia/Damascus": 3,
    "UTC": 0,
}


def resolve_timezone(name: str | None) -> tzinfo:
    timezone_name = name or "UTC"
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        offset = _FIXED_ZONE_OFFSETS.get(timezone_name, 0)
        return timezone(timedelta(hours=offset))
