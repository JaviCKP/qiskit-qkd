from fastapi.testclient import TestClient

from panel.api.app import create_app


def test_health_endpoint_reports_api_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "qiskit-qkd-panel"}
