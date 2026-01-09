"""Main 모듈 테스트."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHealthEndpoints:
    """Health 엔드포인트 테스트."""

    def test_health_endpoint(self, client):
        """Health 엔드포인트 응답 확인."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_ready_endpoint(self, client):
        """Ready 엔드포인트 응답 확인."""
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "active_jobs" in data
        assert "total_subscribers" in data

    def test_root_endpoint(self, client):
        """Root 엔드포인트 응답 확인."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "sse-gateway"
        assert data["status"] == "running"
        assert "version" in data


class TestDocsEndpoints:
    """API 문서 엔드포인트 테스트."""

    def test_docs_endpoint(self, client):
        """Swagger UI 접근 가능."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint(self, client):
        """ReDoc 접근 가능."""
        response = client.get("/redoc")
        assert response.status_code == 200


class TestMetricsEndpoint:
    """Prometheus 메트릭 엔드포인트 테스트."""

    def test_metrics_endpoint(self, client):
        """메트릭 엔드포인트 접근 가능."""
        response = client.get("/metrics")
        # Prometheus 메트릭은 마운트된 앱이므로 리다이렉트 가능
        assert response.status_code in [200, 307]
