from __future__ import annotations

import hashlib
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from telegram import Update

from app.api.errors import register_exception_handlers
from app.api.routes import health, matches, metrics, predictions, providers
from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.logging import request_id_ctx
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import constant_time_equal
from app.telegram.app import build_telegram_application

settings = get_settings()
api_rate_limiter = SlidingWindowRateLimiter(
    limit=settings.api_rate_limit_requests,
    window_seconds=settings.api_rate_limit_window_seconds,
)
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Probabilistic football forecasting backend. Numerical forecasts do not depend on an LLM."
    ),
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "X-API-Key",
            "X-Request-ID",
            "X-Telegram-Bot-Api-Secret-Token",
        ],
    )


@app.middleware("http")
async def request_context_and_security(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    try:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "code": "REQUEST_TOO_LARGE",
                    "message": "request body is too large",
                    "request_id": request_id,
                },
            )
        if request.url.path.startswith("/api/v1/"):
            identity = request.headers.get("X-API-Key") or (
                request.client.host if request.client else "unknown"
            )
            anonymous_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            decision = await api_rate_limiter.check(anonymous_key)
            if not decision.allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": "RATE_LIMITED",
                        "message": "request rate limit exceeded",
                        "request_id": request_id,
                    },
                    headers={"Retry-After": str(decision.retry_after_seconds)},
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/"):
            response.headers["X-RateLimit-Limit"] = str(settings.api_rate_limit_requests)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    finally:
        request_id_ctx.reset(token)


app.include_router(health.router)
app.include_router(providers.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(metrics.router)
register_exception_handlers(app)


@app.post("/telegram/webhook", include_in_schema=True)
async def telegram_webhook(request: Request):
    current = request.app.state.settings
    if not current.telegram_enabled or current.telegram_mode != "webhook":
        raise HTTPException(status_code=404, detail="Telegram webhook is disabled")
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not current.telegram_webhook_secret or not constant_time_equal(
        supplied, current.telegram_webhook_secret
    ):
        raise HTTPException(status_code=401, detail="invalid Telegram webhook secret")
    payload = await request.json()
    application = request.app.state.telegram_application
    if application is None:
        application = build_telegram_application(
            current, request.app.state.football_provider, request.app.state.prediction_service
        )
        await application.initialize()
        await application.start()
        request.app.state.telegram_application = application
    await application.process_update(Update.de_json(payload, application.bot))
    return {"ok": True}
