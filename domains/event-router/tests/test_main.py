"""Main 모듈 테스트."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHealthEndpoints:
    """Health 엔드포인트 테스트."""

    @pytest.fixture
    def client(self, mock_settings):
        """FastAPI TestClient fixture."""
        with patch("config.get_settings", return_value=mock_settings):
            with patch("main.get_settings", return_value=mock_settings):
                from main import app

                with TestClient(app) as test_client:
                    yield test_client

    def test_health_endpoint(self, client):
        """Health 엔드포인트 응답 확인."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self, client):
        """Root 엔드포인트 응답 확인."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "event-router"


class TestMetricsEndpoint:
    """Metrics 엔드포인트 테스트."""

    @pytest.fixture
    def client(self, mock_settings):
        """FastAPI TestClient fixture."""
        with patch("config.get_settings", return_value=mock_settings):
            with patch("main.get_settings", return_value=mock_settings):
                from main import app

                with TestClient(app) as test_client:
                    yield test_client

    def test_metrics_endpoint(self, client):
        """Metrics 엔드포인트 응답 확인."""
        response = client.get("/metrics")
        assert response.status_code == 200
        # Prometheus 포맷 확인
        assert "text/plain" in response.headers.get("content-type", "")
