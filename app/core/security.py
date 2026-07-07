from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlparse

from fastapi import Header, HTTPException, status

from app.core.config import Settings, get_settings

_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|token|authorization|secret)(\s*[=:]\s*)([^\s,;]+)")


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def hash_identifier(value: str, *, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}:{value}".encode()).hexdigest()


def redact_secrets(text: str) -> str:
    return _SECRET_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


def anonymous_slot_id(slot: int) -> str:
    return hashlib.sha256(f"gemini-slot-{slot}".encode()).hexdigest()[:10]


def validate_outbound_url(url: str, settings: Settings) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("only HTTPS provider endpoints are allowed")
    host = (parsed.hostname or "").lower()
    allowed = {item.strip().lower() for item in settings.football_allowed_hosts.split(",") if item}
    if host not in allowed:
        raise ValueError(f"outbound host is not allow-listed: {host}")


async def require_api_key(
    x_api_key: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return
    if x_api_key is None or not constant_time_equal(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
