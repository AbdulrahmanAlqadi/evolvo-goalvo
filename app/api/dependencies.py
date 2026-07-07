from fastapi import Request

from app.services.predictions import PredictionService


def prediction_service(request: Request) -> PredictionService:
    return request.app.state.prediction_service


def football_provider(request: Request):
    return request.app.state.football_provider
