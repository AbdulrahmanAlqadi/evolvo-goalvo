from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx
from app.providers.football.base import ProviderUnavailable


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProviderUnavailable)
    async def provider_unavailable(_request: Request, exc: ProviderUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "code": "FOOTBALL_PROVIDER_UNAVAILABLE",
                "message": "مصدر بيانات المباريات غير متاح حالياً.",
                "request_id": request_id_ctx.get(),
                "retryable": True,
            },
        )

    @app.exception_handler(KeyError)
    async def not_found(_request: Request, _exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "code": "NOT_FOUND",
                "message": "العنصر المطلوب غير موجود.",
                "request_id": request_id_ctx.get(),
                "retryable": False,
            },
        )
