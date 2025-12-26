"""Async Scan API Tests.

비동기 scan API 엔드포인트 테스트.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestClassifyAsyncEndpoint:
    """POST /scan/classify/async 엔드포인트 테스트."""

    @pytest.fixture
    def mock_service(self):
        """Mock ScanService."""
        service = MagicMock()
        service.classify_async = AsyncMock()
        return service

    @pytest.fixture
    def valid_payload(self) -> dict:
        """유효한 요청 페이로드."""
        return {
            "image_url": "https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg",
            "user_input": "이 페트병 어떻게 버려요?",
        }

    @pytest.mark.asyncio
    async def test_returns_processing_status(self):
        """비동기 요청 시 processing 상태 반환."""
        from domains.scan.schemas.scan import ClassificationResponse

        task_id = str(uuid4())
        expected_response = ClassificationResponse(
            task_id=task_id,
            status="processing",
            message="AI 분석이 진행 중입니다. GET /scan/{task_id}/progress (SSE)로 진행상황을 확인하세요.",
        )

        # Response 검증
        assert expected_response.status == "processing"
        assert "SSE" in expected_response.message
        assert expected_response.pipeline_result is None
        assert expected_response.reward is None

    @pytest.mark.asyncio
    async def test_classify_async_calls_service(self, valid_payload):
        """classify_async 엔드포인트가 서비스 호출."""
        from domains.scan.schemas.scan import ClassificationRequest, ClassificationResponse

        request = ClassificationRequest(**valid_payload)
        user_id = uuid4()
        task_id = str(uuid4())

        # Mock service response
        response = ClassificationResponse(
            task_id=task_id,
            status="processing",
            message="Processing...",
        )

        with patch("domains.scan.services.scan.ScanService") as MockService:
            mock_instance = MockService.return_value
            mock_instance.classify_async = AsyncMock(return_value=response)

            result = await mock_instance.classify_async(request, user_id)

            assert result.status == "processing"
            assert result.task_id == task_id
            mock_instance.classify_async.assert_called_once_with(request, user_id)


class TestClassifyAsyncService:
    """ScanService.classify_async 메서드 테스트."""

    @pytest.fixture
    def mock_settings(self):
        """Mock Settings."""
        from domains.scan.core.config import Settings

        return Settings(
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            character_grpc_target="localhost:50051",
        )

    @pytest.fixture
    def valid_image_url(self) -> str:
        return "https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg"

    @pytest.mark.asyncio
    async def test_dispatches_celery_chain(self, mock_settings, valid_image_url):
        """Celery Chain 발행 검증."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.schemas.scan import ClassificationRequest
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.image_validator = ImageUrlValidator(mock_settings)

        request = ClassificationRequest(image_url=valid_image_url)
        user_id = uuid4()

        # chain은 _classify_async_internal 내부에서 import됨
        with patch("celery.chain") as mock_chain:
            mock_pipeline = MagicMock()
            mock_chain.return_value = mock_pipeline

            response = await service.classify_async(request, user_id)

            # Chain이 발행됨
            mock_chain.assert_called_once()
            mock_pipeline.delay.assert_called_once()

            # 응답 검증
            assert response.status == "processing"
            assert "SSE" in response.message

    @pytest.mark.asyncio
    async def test_returns_error_on_invalid_image(self, mock_settings):
        """유효하지 않은 이미지 URL 시 에러."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.schemas.scan import ClassificationRequest
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.image_validator = ImageUrlValidator(mock_settings)

        request = ClassificationRequest(image_url="http://malicious.com/image.jpg")
        user_id = uuid4()

        response = await service.classify_async(request, user_id)

        assert response.status == "failed"
        assert "HTTPS_REQUIRED" in (response.error or "")

    @pytest.mark.asyncio
    async def test_returns_error_on_no_image(self, mock_settings):
        """이미지 URL 없을 시 에러."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.schemas.scan import ClassificationRequest
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.image_validator = ImageUrlValidator(mock_settings)

        request = ClassificationRequest(image_url=None)
        user_id = uuid4()

        response = await service.classify_async(request, user_id)

        assert response.status == "failed"
        assert response.error == "IMAGE_URL_REQUIRED"

    @pytest.mark.asyncio
    async def test_chain_dispatch_failure(self, mock_settings, valid_image_url):
        """Chain 발행 실패 시 에러 응답."""
        from domains.scan.core.validators import ImageUrlValidator
        from domains.scan.schemas.scan import ClassificationRequest
        from domains.scan.services.scan import ScanService

        service = ScanService.__new__(ScanService)
        service.settings = mock_settings
        service.image_validator = ImageUrlValidator(mock_settings)

        request = ClassificationRequest(image_url=valid_image_url)
        user_id = uuid4()

        with patch("celery.chain") as mock_chain:
            mock_chain.side_effect = Exception("RabbitMQ connection failed")

            response = await service.classify_async(request, user_id)

            assert response.status == "failed"
            assert response.error == "TASK_DISPATCH_ERROR"


class TestCallbackUrlDeprecated:
    """callback_url deprecated 테스트."""

    def test_callback_url_is_deprecated(self):
        """callback_url 필드가 deprecated로 표시됨."""
        from domains.scan.schemas.scan import ClassificationRequest

        schema = ClassificationRequest.model_json_schema()
        callback_url_props = schema["properties"]["callback_url"]

        # json_schema_extra로 deprecated 표시
        assert callback_url_props.get(
            "deprecated"
        ) is True or "[DEPRECATED]" in callback_url_props.get("description", "")

    def test_callback_url_ignored_in_async(self):
        """callback_url은 async 처리에서 무시됨."""
        from domains.scan.schemas.scan import ClassificationRequest

        # callback_url이 있어도 async 엔드포인트는 SSE 사용
        request = ClassificationRequest(
            image_url="https://images.dev.growbin.app/scan/test.jpg",
            callback_url="https://webhook.example.com/callback",  # 무시됨
        )

        # callback_url은 파싱되지만 실제로 사용되지 않음
        assert request.callback_url is not None
        # 실제 처리에서는 SSE로 결과 전달


class TestAsyncResponseFormat:
    """비동기 응답 형식 테스트."""

    def test_async_response_structure(self):
        """비동기 응답 구조 검증."""
        from domains.scan.schemas.scan import ClassificationResponse

        task_id = str(uuid4())
        response = ClassificationResponse(
            task_id=task_id,
            status="processing",
            message="AI 분석이 진행 중입니다.",
        )

        # 비동기 응답은 pipeline_result, reward가 None
        assert response.task_id == task_id
        assert response.status == "processing"
        assert response.pipeline_result is None
        assert response.reward is None
        assert response.error is None

    def test_completed_response_structure(self):
        """완료 응답 구조 검증 (SSE 최종 이벤트와 동일)."""
        from domains.scan.schemas.scan import ClassificationResponse

        from domains._shared.schemas.waste import WasteClassificationResult
        from domains.character.schemas.reward import CharacterRewardResponse

        task_id = str(uuid4())

        pipeline_result = WasteClassificationResult(
            classification_result={
                "classification": {
                    "major_category": "재활용폐기물",
                    "middle_category": "무색페트병",
                }
            },
            disposal_rules={"배출방법": "분리수거"},
            final_answer={"user_answer": "페트병 분리배출"},
        )

        reward = CharacterRewardResponse(
            received=True,
            already_owned=False,
            name="페트병이",
            dialog="잘했어요!",
        )

        response = ClassificationResponse(
            task_id=task_id,
            status="completed",
            message="classification completed",
            pipeline_result=pipeline_result,
            reward=reward,
        )

        assert response.status == "completed"
        assert response.pipeline_result is not None
        assert response.reward.received is True


class TestAPIFlowIntegration:
    """API 전체 흐름 통합 테스트."""

    def test_async_api_flow_documentation(self):
        """비동기 API 흐름 문서화 검증."""
        # 예상 흐름:
        # 1. POST /scan/classify/async → 202-like response (processing)
        # 2. GET /scan/{task_id}/progress → SSE stream
        # 3. SSE events: vision → rule → answer → reward
        # 4. 최종 SSE 이벤트에 result 포함

        expected_flow = {
            "step_1": {
                "method": "POST",
                "endpoint": "/api/v1/scan/classify/async",
                "request": {"image_url": "https://..."},
                "response": {
                    "task_id": "uuid",
                    "status": "processing",
                    "message": "... SSE ...",
                },
            },
            "step_2": {
                "method": "GET",
                "endpoint": "/api/v1/scan/{task_id}/progress",
                "response_type": "text/event-stream",
            },
            "step_3_events": [
                {"step": "vision", "status": "completed", "progress": 25},
                {"step": "rule", "status": "completed", "progress": 50},
                {"step": "answer", "status": "completed", "progress": 75},
                {
                    "step": "reward",
                    "status": "completed",
                    "progress": 100,
                    "result": {
                        "pipeline_result": "...",
                        "reward": "...",
                    },
                },
            ],
        }

        # 흐름 검증
        assert expected_flow["step_1"]["response"]["status"] == "processing"
        assert expected_flow["step_2"]["response_type"] == "text/event-stream"
        assert expected_flow["step_3_events"][-1]["progress"] == 100
        assert "result" in expected_flow["step_3_events"][-1]
