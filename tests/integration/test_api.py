from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

HEADERS = {"X-API-Key": get_settings().api_key}


def test_health_and_openapi():
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["database"] is True


def test_authentication_required():
    with TestClient(app) as client:
        assert client.get("/api/v1/matches").status_code == 401
        assert client.get("/api/v1/matches", headers=HEADERS).status_code == 200


def test_prediction_endpoint_and_history():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/predictions/pre-match", headers=HEADERS, json={"match_id": "demo-match-001"}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        values = payload["outcomes_90_minutes"]
        assert abs(values["home_win"] + values["draw"] + values["away_win"] - 1) < 1e-8
        assert payload["qualification"] is not None
        history = client.get("/api/v1/predictions/demo-match-001/history", headers=HEADERS)
        assert history.status_code == 200
        assert len(history.json()) >= 1
