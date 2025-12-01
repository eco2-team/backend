from fastapi import FastAPI
from fastapi.testclient import TestClient

from domains._shared.observability import PROMETHEUS_METRICS_PATH, register_http_metrics


def test_metrics_endpoint_emits_domain_labels():
    app = FastAPI()
    register_http_metrics(app, domain="demo", service="demo-api")

    @app.get("/ping")
    async def ping():
        return {"message": "pong"}

    client = TestClient(app)
    response = client.get("/ping")
    assert response.status_code == 200

    metrics_response = client.get(PROMETHEUS_METRICS_PATH)
    assert metrics_response.status_code == 200
    payload = metrics_response.content

    assert b"http_requests_total" in payload
    assert b'domain="demo"' in payload
    assert b'status_class="2xx"' in payload
