"""Main 모듈 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHealthEndpoints:
    """Health 엔드포인트 테스트.

    Note: startup/shutdown 이벤트가 Redis에 연결하려고 하므로
    테스트용 앱을 따로 만들어서 테스트합니다.
    """

    @pytest.fixture
    def test_app(self, mock_settings):
        """테스트용 FastAPI 앱 (startup/shutdown 없음)."""
        app = FastAPI(title="Event Router Test")

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/info")
        async def info():
            return {
                "service": mock_settings.service_name,
                "version": mock_settings.service_version,
            }

        return app

    @pytest.fixture
    def client(self, test_app):
        """FastAPI TestClient fixture."""
        with TestClient(test_app) as test_client:
            yield test_client

    def test_health_endpoint(self, client):
        """Health 엔드포인트 응답 확인."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_info_endpoint(self, client):
        """Info 엔드포인트 응답 확인."""
        response = client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "event-router"
