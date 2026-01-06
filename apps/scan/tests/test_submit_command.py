"""SubmitClassificationCommand Tests.

Clean Architecture 버전 테스트.
- 모델명 기반 선택 (provider enum 제거)
- 멱등성 테스트 추가
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

# 테스트용 환경변수 설정 (Settings 로드 전에 필요)
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from scan.application.classify.commands import (
    SubmitClassificationCommand,
    SubmitClassificationRequest,
)


class TestSubmitClassificationRequest:
    """SubmitClassificationRequest DTO 테스트."""

    def test_default_model(self):
        """기본 모델은 gpt-5.2."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )
        assert request.model == "gpt-5.2"

    def test_explicit_model(self):
        """명시적 모델 설정."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            model="gemini-2.5-flash",
        )
        assert request.model == "gemini-2.5-flash"

    def test_optional_user_input(self):
        """user_input은 선택적."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )
        assert request.user_input is None

    def test_with_user_input(self):
        """user_input 포함."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            user_input="이거 어떻게 버려?",
        )
        assert request.user_input == "이거 어떻게 버려?"

    def test_optional_idempotency_key(self):
        """idempotency_key는 선택적."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )
        assert request.idempotency_key is None

    def test_with_idempotency_key(self):
        """idempotency_key 포함."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            idempotency_key="unique-key-123",
        )
        assert request.idempotency_key == "unique-key-123"


class TestSubmitClassificationCommand:
    """SubmitClassificationCommand 테스트."""

    @pytest.fixture
    def mock_event_publisher(self):
        """Mock EventPublisher."""
        publisher = MagicMock()
        publisher.publish_stage_event = MagicMock()
        return publisher

    @pytest.fixture
    def mock_idempotency_cache(self):
        """Mock IdempotencyCache."""
        cache = MagicMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        return cache

    @pytest.fixture
    def mock_celery_app(self):
        """Mock Celery App."""
        app = MagicMock()
        signature_mock = MagicMock()
        app.signature.return_value = signature_mock
        return app

    @pytest.fixture
    def command(
        self,
        mock_event_publisher,
        mock_idempotency_cache,
        mock_celery_app,
        mock_celery_chain,
    ):
        """Command 인스턴스."""
        return SubmitClassificationCommand(
            event_publisher=mock_event_publisher,
            idempotency_cache=mock_idempotency_cache,
            celery_app=mock_celery_app,
        )

    @pytest.mark.anyio
    async def test_execute_returns_job_id(self, command, mock_celery_chain):
        """execute()는 job_id를 반환."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )

        response = await command.execute(request)

        assert response.job_id is not None
        assert len(response.job_id) == 36  # UUID format

    @pytest.mark.anyio
    async def test_execute_publishes_queued_event(
        self, command, mock_event_publisher, mock_celery_chain
    ):
        """execute()는 queued 이벤트를 발행."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )

        await command.execute(request)

        mock_event_publisher.publish_stage_event.assert_called_once()
        call_kwargs = mock_event_publisher.publish_stage_event.call_args.kwargs
        assert call_kwargs["stage"] == "queued"
        assert call_kwargs["status"] == "started"

    @pytest.mark.anyio
    async def test_execute_passes_model_to_chain(self, command, mock_celery_app, mock_celery_chain):
        """execute()는 모델명을 Celery chain에 전달."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            model="gemini-2.5-flash",
        )

        await command.execute(request)

        # signature 호출 확인
        signature_calls = mock_celery_app.signature.call_args_list
        vision_call = signature_calls[0]

        # kwargs에 model 포함 확인
        assert "kwargs" in vision_call.kwargs
        assert vision_call.kwargs["kwargs"]["model"] == "gemini-2.5-flash"

    @pytest.mark.anyio
    async def test_execute_stream_url_format(self, command, mock_celery_chain):
        """execute()는 올바른 stream_url 형식 반환."""
        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
        )

        response = await command.execute(request)

        assert response.stream_url == f"/api/v1/scan/{response.job_id}/events"
        assert response.result_url == f"/api/v1/scan/{response.job_id}/result"


class TestIdempotency:
    """멱등성(Idempotency) 테스트."""

    @pytest.fixture
    def mock_event_publisher(self):
        """Mock EventPublisher."""
        publisher = MagicMock()
        publisher.publish_stage_event = MagicMock()
        return publisher

    @pytest.fixture
    def mock_celery_app(self):
        """Mock Celery App."""
        app = MagicMock()
        signature_mock = MagicMock()
        app.signature.return_value = signature_mock
        return app

    @pytest.mark.anyio
    async def test_idempotency_cache_hit(
        self, mock_event_publisher, mock_celery_app, mock_celery_chain
    ):
        """동일한 idempotency_key로 재요청 시 캐시된 응답 반환."""
        cached_response = {
            "job_id": "cached-job-id",
            "stream_url": "/api/v1/scan/cached-job-id/events",
            "result_url": "/api/v1/scan/cached-job-id/result",
            "status": "queued",
        }

        mock_idempotency_cache = MagicMock()
        mock_idempotency_cache.get = AsyncMock(return_value=cached_response)
        mock_idempotency_cache.set = AsyncMock()

        command = SubmitClassificationCommand(
            event_publisher=mock_event_publisher,
            idempotency_cache=mock_idempotency_cache,
            celery_app=mock_celery_app,
        )

        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            idempotency_key="unique-key-123",
        )

        response = await command.execute(request)

        # 캐시된 응답 반환
        assert response.job_id == "cached-job-id"
        # Celery chain은 호출되지 않음
        mock_celery_app.signature.assert_not_called()
        # 이벤트 발행도 되지 않음
        mock_event_publisher.publish_stage_event.assert_not_called()

    @pytest.mark.anyio
    async def test_idempotency_cache_miss_then_save(
        self, mock_event_publisher, mock_celery_app, mock_celery_chain
    ):
        """idempotency_key가 있지만 캐시 miss 시 새 작업 생성 후 저장."""
        mock_idempotency_cache = MagicMock()
        mock_idempotency_cache.get = AsyncMock(return_value=None)
        mock_idempotency_cache.set = AsyncMock()

        command = SubmitClassificationCommand(
            event_publisher=mock_event_publisher,
            idempotency_cache=mock_idempotency_cache,
            celery_app=mock_celery_app,
        )

        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            idempotency_key="unique-key-123",
        )

        response = await command.execute(request)

        # 새 job_id 생성
        assert response.job_id is not None
        assert len(response.job_id) == 36
        # 캐시에 저장
        mock_idempotency_cache.set.assert_called_once()
        call_kwargs = mock_idempotency_cache.set.call_args.kwargs
        assert call_kwargs["key"] == "unique-key-123"

    @pytest.mark.anyio
    async def test_no_idempotency_key_skips_cache(
        self, mock_event_publisher, mock_celery_app, mock_celery_chain
    ):
        """idempotency_key가 없으면 캐시 체크 건너뜀."""
        mock_idempotency_cache = MagicMock()
        mock_idempotency_cache.get = AsyncMock(return_value=None)
        mock_idempotency_cache.set = AsyncMock()

        command = SubmitClassificationCommand(
            event_publisher=mock_event_publisher,
            idempotency_cache=mock_idempotency_cache,
            celery_app=mock_celery_app,
        )

        request = SubmitClassificationRequest(
            user_id="user-1",
            image_url="https://example.com/image.jpg",
            # idempotency_key 없음
        )

        await command.execute(request)

        # 캐시 get은 호출되지 않음
        mock_idempotency_cache.get.assert_not_called()
        # 캐시 set도 호출되지 않음
        mock_idempotency_cache.set.assert_not_called()
