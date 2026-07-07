from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import prediction_service
from app.core.security import require_api_key
from app.observability.metrics import SSE_CLIENTS
from app.schemas.predictions import (
    PredictionResponse,
    PreMatchPredictionRequest,
    RefreshPredictionRequest,
)
from app.services.predictions import PredictionService

router = APIRouter(
    prefix="/api/v1/predictions", tags=["predictions"], dependencies=[Depends(require_api_key)]
)


@router.post("/pre-match", response_model=PredictionResponse)
async def create_pre_match(
    payload: PreMatchPredictionRequest, service: PredictionService = Depends(prediction_service)
):
    return await service.pre_match(payload.match_id, payload.generated_at)


@router.post("/{match_id}/refresh", response_model=PredictionResponse)
async def refresh_prediction(
    match_id: str,
    payload: RefreshPredictionRequest,
    service: PredictionService = Depends(prediction_service),
):
    match = await service.provider.get_match(match_id)
    if match.status.value in {"LIVE", "HALF_TIME", "EXTRA_TIME", "PENALTIES"} or payload.force:
        return await service.live(match_id)
    return await service.pre_match(match_id)


@router.get("/{match_id}/latest", response_model=PredictionResponse)
async def latest_prediction(
    match_id: str, service: PredictionService = Depends(prediction_service)
):
    result = await service.latest(match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return result


@router.get("/{match_id}/history", response_model=list[PredictionResponse])
async def prediction_history(
    match_id: str,
    limit: int = Query(50, ge=1, le=200),
    service: PredictionService = Depends(prediction_service),
):
    return await service.history(match_id, limit)


@router.get("/{match_id}/explanation")
async def prediction_explanation(
    match_id: str, service: PredictionService = Depends(prediction_service)
):
    result = await service.latest(match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return result.explanation


@router.get("/{match_id}/stream")
async def prediction_stream(
    match_id: str, request: Request, service: PredictionService = Depends(prediction_service)
):
    queue = await service.broker.subscribe(match_id)
    latest = await service.latest(match_id)

    async def events():
        SSE_CLIENTS.inc()
        try:
            if latest:
                payload = json.dumps(latest.model_dump(mode="json"), ensure_ascii=False)
                yield f"event: prediction\ndata: {payload}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    prediction = await asyncio.wait_for(queue.get(), timeout=15)
                    payload = json.dumps(prediction.model_dump(mode="json"), ensure_ascii=False)
                    yield f"event: prediction\ndata: {payload}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            SSE_CLIENTS.dec()
            await service.broker.unsubscribe(match_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
