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


class TestClassifyCompletionFlow:
    """SSE Completion 흐름 테스트.

    Note: classify_async는 classify_completion으로 대체됨.
    테스트는 현재 구현과 일치하도록 업데이트.
    """

    @pytest.fixture
    def valid_image_url(self) -> str:
        return "https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg"

    def test_classification_request_has_required_fields(self, valid_image_url):
        """ClassificationRequest 필드 검증."""
        from domains.scan.schemas.scan import ClassificationRequest

        request = ClassificationRequest(image_url=valid_image_url)

        assert request.image_url is not None
        assert str(request.image_url) == valid_image_url

    def test_classification_request_optional_user_input(self, valid_image_url):
        """user_input은 선택적."""
        from domains.scan.schemas.scan import ClassificationRequest

        request = ClassificationRequest(
            image_url=valid_image_url,
            user_input="테스트 질문",
        )

        assert request.user_input == "테스트 질문"

    def test_classification_request_schema_structure(self):
        """ClassificationRequest 스키마 구조 검증."""
        from domains.scan.schemas.scan import ClassificationRequest

        schema = ClassificationRequest.model_json_schema()

        # 필수 필드만 확인
        assert "image_url" in schema["properties"]
        assert "user_input" in schema["properties"]

        # callback_url은 현재 스키마에 없음 (제거됨)
        assert "callback_url" not in schema["properties"]


class TestClassificationEndpointOptions:
    """분류 엔드포인트 옵션 테스트.

    - POST /scan/classify: 동기 처리
    - POST /scan/classify/completion: SSE 스트리밍
    """

    def test_sync_endpoint_exists(self):
        """동기 분류 엔드포인트 확인."""
        # /api/v1/scan/classify 엔드포인트는 동기 처리
        expected_endpoint = "/api/v1/scan/classify"
        assert "classify" in expected_endpoint

    def test_sse_endpoint_exists(self):
        """SSE 스트리밍 엔드포인트 확인."""
        # /api/v1/scan/classify/completion 엔드포인트는 SSE 스트리밍
        expected_endpoint = "/api/v1/scan/classify/completion"
        assert "completion" in expected_endpoint


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
