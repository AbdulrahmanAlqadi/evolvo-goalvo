from __future__ import annotations

import logging
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

from app.core.config import Settings
from app.core.security import redact_secrets

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        return True


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.addFilter(RequestContextFilter())
    if settings.log_format == "json":
        handler.setFormatter(
            JsonFormatter("%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s")
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
