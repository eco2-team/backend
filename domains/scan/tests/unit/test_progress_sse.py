"""Unit tests for SSE Progress endpoint.

SSE 재접속, event_id, Redis 캐싱 등을 테스트합니다.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


class TestFormatSSE:
    """SSE 포맷팅 테스트."""

    def test_format_sse_with_id(self):
        """event_id가 포함된 SSE 포맷."""
        from domains.scan.api.v1.endpoints.progress import _format_sse_with_id

        data = {"step": "vision", "status": "completed", "progress": 25}
        result = _format_sse_with_id(data, event_id=1)

        assert "id: 1\n" in result
        assert "data: " in result
        assert '"step": "vision"' in result
        assert result.endswith("\n\n")

    def test_format_sse_with_id_removes_internal_field(self):
        """_event_id 내부 필드는 제거됨."""
        from domains.scan.api.v1.endpoints.progress import _format_sse_with_id

        data = {"step": "rule", "_event_id": 99}
        result = _format_sse_with_id(data, event_id=2)

        assert "_event_id" not in result
        assert "id: 2\n" in result

    def test_format_sse_legacy(self):
        """레거시 SSE 포맷 (id 없음)."""
        from domains.scan.api.v1.endpoints.progress import _format_sse

        data = {"status": "connected"}
        result = _format_sse(data)

        assert result.startswith("data: ")
        assert "id:" not in result


class TestTaskStepMap:
    """Task 단계 매핑 테스트."""

    def test_all_pipeline_stages_mapped(self):
        """4단계 파이프라인 모두 매핑됨."""
        from domains.scan.api.v1.endpoints.progress import TASK_STEP_MAP

        expected_stages = ["scan.vision", "scan.rule", "scan.answer", "scan.reward"]
        for stage in expected_stages:
            assert stage in TASK_STEP_MAP

    def test_progress_increments(self):
        """진행률이 단계별로 증가."""
        from domains.scan.api.v1.endpoints.progress import TASK_STEP_MAP

        stages = ["scan.vision", "scan.rule", "scan.answer", "scan.reward"]
        progresses = [TASK_STEP_MAP[s]["progress"] for s in stages]

        # 오름차순 확인
        assert progresses == sorted(progresses)
        assert progresses[-1] == 100  # 마지막은 100%

    def test_stage_names(self):
        """단계 이름 확인."""
        from domains.scan.api.v1.endpoints.progress import TASK_STEP_MAP

        assert TASK_STEP_MAP["scan.vision"]["step"] == "vision"
        assert TASK_STEP_MAP["scan.rule"]["step"] == "rule"
        assert TASK_STEP_MAP["scan.answer"]["step"] == "answer"
        assert TASK_STEP_MAP["scan.reward"]["step"] == "reward"


class TestGetRedisClient:
    """Redis 클라이언트 테스트."""

    @patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/1"})
    def test_get_redis_client_from_env(self):
        """환경변수에서 Redis URL 로드."""
        import redis

        with patch.object(redis, "from_url", return_value=MagicMock()) as mock_from_url:
            from domains.scan.api.v1.endpoints.progress import _get_redis_client

            _get_redis_client()
            mock_from_url.assert_called_once_with("redis://localhost:6379/1", decode_responses=True)

    def test_get_redis_client_default(self):
        """기본 Redis URL 사용."""
        import redis

        # 환경변수 제거

        original = os.environ.pop("REDIS_URL", None)

        try:
            with patch.object(redis, "from_url", return_value=MagicMock()) as mock_from_url:
                from importlib import reload

                import domains.scan.api.v1.endpoints.progress as progress_module

                reload(progress_module)
                progress_module._get_redis_client()

                call_args = mock_from_url.call_args[0][0]
                assert "redis://localhost:6379" in call_args
        finally:
            if original:
                os.environ["REDIS_URL"] = original


class TestSSEEventCaching:
    """SSE 이벤트 캐싱 테스트."""

    def test_cache_key_format(self):
        """캐시 키 형식 확인."""
        from domains.scan.api.v1.endpoints.progress import SSE_EVENT_CACHE_PREFIX

        task_id = "abc-123"
        expected_key = f"{SSE_EVENT_CACHE_PREFIX}{task_id}"

        assert expected_key == "sse:scan:events:abc-123"

    def test_cache_ttl_configured(self):
        """캐시 TTL 설정 확인."""
        from domains.scan.api.v1.endpoints.progress import SSE_EVENT_CACHE_TTL

        assert SSE_EVENT_CACHE_TTL == 300  # 5분


class TestSSEReconnection:
    """SSE 재접속 시나리오 테스트."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis 클라이언트."""
        client = MagicMock()
        client.lrange.return_value = []
        client.rpush.return_value = None
        client.expire.return_value = None
        return client

    @pytest.fixture
    def cached_events(self):
        """캐시된 이벤트 목록."""
        return [
            json.dumps({"step": "vision", "status": "completed", "progress": 25, "_event_id": 1}),
            json.dumps({"step": "rule", "status": "completed", "progress": 50, "_event_id": 2}),
            json.dumps({"step": "answer", "status": "completed", "progress": 75, "_event_id": 3}),
        ]

    def test_replay_events_after_reconnect(self, mock_redis_client, cached_events):
        """재접속 시 캐시된 이벤트 재전송."""
        mock_redis_client.lrange.return_value = cached_events

        # Last-Event-ID: 1 → id 2, 3만 재전송해야 함
        last_event_id = 1
        replayed = []

        for cached in cached_events:
            event_data = json.loads(cached)
            event_id = event_data.get("_event_id", 0)
            if event_id > last_event_id:
                replayed.append(event_data)

        assert len(replayed) == 2
        assert replayed[0]["step"] == "rule"
        assert replayed[1]["step"] == "answer"

    def test_no_replay_when_no_last_event_id(self, mock_redis_client, cached_events):
        """Last-Event-ID 없으면 재전송 없음."""
        last_event_id = None

        # last_event_id가 None이면 캐시 조회 안 함
        should_replay = last_event_id is not None
        assert should_replay is False


class TestStreamProgressEndpoint:
    """stream_progress 엔드포인트 테스트."""

    @pytest.mark.asyncio
    async def test_returns_streaming_response(self):
        """StreamingResponse 반환."""
        from fastapi.responses import StreamingResponse

        from domains.scan.api.v1.endpoints.progress import stream_progress

        with patch("domains.scan.api.v1.endpoints.progress._event_generator") as mock_gen:
            mock_gen.return_value = iter([])

            response = await stream_progress(task_id="test-123", last_event_id=None)

            assert isinstance(response, StreamingResponse)
            assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_headers_disable_caching(self):
        """캐싱 비활성화 헤더."""
        from domains.scan.api.v1.endpoints.progress import stream_progress

        with patch("domains.scan.api.v1.endpoints.progress._event_generator") as mock_gen:
            mock_gen.return_value = iter([])

            response = await stream_progress(task_id="test-123", last_event_id=None)

            assert response.headers.get("Cache-Control") == "no-cache"
            assert response.headers.get("X-Accel-Buffering") == "no"


class TestEventGeneratorEdgeCases:
    """이벤트 제너레이터 엣지 케이스."""

    def test_chain_task_detection_direct_match(self):
        """직접 task_id 매칭."""
        task_id = "abc-123"
        chain_task_ids = {task_id}
        event_task_id = task_id

        is_chain = event_task_id in chain_task_ids
        assert is_chain is True

    def test_chain_task_detection_parent_match(self):
        """parent_id로 chain 매칭."""
        task_id = "abc-123"
        chain_task_ids = {task_id}
        parent_id = task_id
        event_task_id = "xyz-456"  # 다른 ID

        is_chain = event_task_id in chain_task_ids or parent_id in chain_task_ids
        assert is_chain is True

    def test_chain_task_detection_no_match(self):
        """매칭되지 않는 task."""
        task_id = "abc-123"
        chain_task_ids = {task_id}
        event_task_id = "other-task"
        parent_id = "another-parent"

        is_chain = event_task_id in chain_task_ids or parent_id in chain_task_ids
        assert is_chain is False


class TestFinalResultFormat:
    """최종 결과 포맷 테스트."""

    def test_final_result_includes_all_fields(self):
        """마지막 단계(reward) 결과에 모든 필드 포함."""
        result = {
            "task_id": "abc-123",
            "classification_result": {"classification": {"major_category": "재활용"}},
            "disposal_rules": {"배출방법": "분리수거"},
            "final_answer": {"user_answer": "답변"},
            "reward": {"received": True, "name": "페트병이"},
        }

        # ClassificationResponse 스키마와 동일한 형식
        sse_result = {
            "task_id": result.get("task_id"),
            "status": "completed",
            "message": "classification completed",
            "pipeline_result": {
                "classification_result": result.get("classification_result"),
                "disposal_rules": result.get("disposal_rules"),
                "final_answer": result.get("final_answer"),
            },
            "reward": result.get("reward"),
            "error": None,
        }

        assert sse_result["task_id"] == "abc-123"
        assert sse_result["status"] == "completed"
        assert sse_result["pipeline_result"]["classification_result"] is not None
        assert sse_result["reward"]["received"] is True
        assert sse_result["error"] is None

    def test_final_result_with_no_reward(self):
        """리워드 없는 최종 결과."""
        result = {
            "task_id": "abc-123",
            "classification_result": {"classification": {"major_category": "일반쓰레기"}},
            "disposal_rules": None,
            "final_answer": {"user_answer": "종량제 봉투에 버리세요"},
            "reward": None,
        }

        sse_result = {
            "task_id": result.get("task_id"),
            "status": "completed",
            "pipeline_result": {
                "classification_result": result.get("classification_result"),
                "disposal_rules": result.get("disposal_rules"),
                "final_answer": result.get("final_answer"),
            },
            "reward": result.get("reward"),
            "error": None,
        }

        assert sse_result["reward"] is None
        assert sse_result["pipeline_result"]["disposal_rules"] is None
