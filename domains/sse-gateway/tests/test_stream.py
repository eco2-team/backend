"""Stream 엔드포인트 테스트."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStreamEndpoint:
    """SSE Stream 엔드포인트 테스트."""

    def test_stream_invalid_job_id_short(self, client):
        """짧은 job_id 거부."""
        response = client.get("/api/v1/stream/abc")
        assert response.status_code == 400
        data = response.json()
        assert "Invalid job_id" in data["detail"]

    def test_stream_invalid_job_id_empty(self, client):
        """빈 job_id 거부 (404 - 라우트 없음)."""
        response = client.get("/api/v1/stream/")
        # 빈 경로는 404 또는 다른 라우트로 매칭
        assert response.status_code in [404, 405]

    def test_stream_valid_job_id(self, client):
        """유효한 job_id 형식 (길이 >= 10)."""
        from core.broadcast_manager import SSEBroadcastManager

        # SSEBroadcastManager를 mock
        async def mock_subscribe(job_id):
            yield {"stage": "done", "status": "success"}

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            # SSE 엔드포인트 호출 - 200 응답과 text/event-stream 확인
            response = client.get("/api/v1/stream/valid-job-id-12345")
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")


class TestEventGenerator:
    """event_generator 함수 테스트."""

    @pytest.mark.asyncio
    async def test_event_generator_keepalive(self):
        """keepalive 이벤트 포맷."""
        from api.v1.stream import event_generator
        from core.broadcast_manager import SSEBroadcastManager

        async def mock_subscribe(job_id):
            yield {"type": "keepalive", "timestamp": "2025-01-01T00:00:00"}
            return

        # Mock 설정
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            events = []
            async for event in event_generator("test-job-id-12345", mock_request):
                events.append(event)
                break  # 첫 이벤트만

            assert len(events) == 1
            assert events[0]["event"] == "keepalive"

    @pytest.mark.asyncio
    async def test_event_generator_stage_event(self):
        """stage 이벤트 포맷."""
        import json

        from api.v1.stream import event_generator
        from core.broadcast_manager import SSEBroadcastManager

        async def mock_subscribe(job_id):
            yield {"stage": "vision", "status": "success", "progress": 25}
            return

        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            events = []
            async for event in event_generator("test-job-id-12345", mock_request):
                events.append(event)
                break

            assert len(events) == 1
            assert events[0]["event"] == "vision"
            data = json.loads(events[0]["data"])
            assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_event_generator_error_event(self):
        """error 이벤트 포맷."""
        import json

        from api.v1.stream import event_generator
        from core.broadcast_manager import SSEBroadcastManager

        async def mock_subscribe(job_id):
            yield {"type": "error", "error": "timeout", "message": "Maximum wait time exceeded"}
            return

        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            events = []
            async for event in event_generator("test-job-id-12345", mock_request):
                events.append(event)
                break

            assert len(events) == 1
            assert events[0]["event"] == "error"
            data = json.loads(events[0]["data"])
            assert data["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_event_generator_failed_status(self):
        """failed status 이벤트 포맷."""

        from api.v1.stream import event_generator
        from core.broadcast_manager import SSEBroadcastManager

        async def mock_subscribe(job_id):
            yield {"stage": "vision", "status": "failed", "error": "API error"}
            return

        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            events = []
            async for event in event_generator("test-job-id-12345", mock_request):
                events.append(event)
                break

            assert len(events) == 1
            assert events[0]["event"] == "error"

    @pytest.mark.asyncio
    async def test_event_generator_client_disconnect(self):
        """클라이언트 연결 해제 감지."""
        from api.v1.stream import event_generator
        from core.broadcast_manager import SSEBroadcastManager

        async def mock_subscribe(job_id):
            yield {"stage": "vision", "status": "success"}
            yield {"stage": "rule", "status": "success"}
            yield {"stage": "answer", "status": "success"}

        mock_request = AsyncMock()
        # 첫 번째 호출은 False, 두 번째부터 True (연결 해제)
        mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

        mock_manager = AsyncMock()
        mock_manager.subscribe = mock_subscribe

        with patch.object(SSEBroadcastManager, "get_instance", return_value=mock_manager):
            events = []
            async for event in event_generator("test-job-id-12345", mock_request):
                events.append(event)

            # 연결 해제 전 1개 이벤트만 수신
            assert len(events) == 1
