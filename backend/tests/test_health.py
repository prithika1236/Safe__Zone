from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "SafeZone"
    assert "version" in data


def test_api_subrouters_status():
    for sub in ["auth", "crimes", "sos", "patrols", "prp", "admin"]:
        response = client.get(f"/api/v1/{sub}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["module"] == sub
        assert data["status"] == "ready"
