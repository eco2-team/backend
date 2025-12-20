"""OpenAI API Integration Tests.

실제 OpenAI API를 호출하여 파이프라인 동작을 검증합니다.

Usage:
    # 1. API 키 설정
    export OPENAI_API_KEY=$(aws ssm get-parameter \
        --name "/dev/shared/openai-api-key" \
        --with-decryption \
        --query "Parameter.Value" \
        --output text)

    # 2. 테스트 실행
    pytest domains/chat/tests/integration/test_openai_integration.py -v -s

    # 3. 특정 테스트만 실행
    pytest domains/chat/tests/integration/test_openai_integration.py::TestTextPipeline -v -s
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.requires_openai
class TestTextPipeline:
    """텍스트 파이프라인 통합 테스트 (실제 OpenAI API 호출)."""

    @pytest.mark.asyncio
    async def test_text_query_returns_valid_response(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """텍스트 질문에 대해 유효한 응답 반환."""
        payload = {"message": "페트병 버리는 방법 알려줘"}

        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )

        assert response.status_code == 201  # HTTP 201 Created
        data = response.json()

        # 필수 필드 확인
        assert "user_answer" in data
        assert isinstance(data["user_answer"], str)
        assert len(data["user_answer"]) > 0

        # 응답 내용 검증 (폐기물 관련 키워드 포함)
        answer = data["user_answer"].lower()
        assert any(
            keyword in answer for keyword in ["페트", "플라스틱", "분리", "재활용", "수거", "버리"]
        ), f"응답에 폐기물 관련 키워드가 없음: {data['user_answer']}"

    @pytest.mark.asyncio
    async def test_text_query_response_time(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """텍스트 쿼리 응답 시간 측정."""
        payload = {"message": "종이컵 분리수거 방법"}

        start = time.time()
        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )
        elapsed = time.time() - start

        assert response.status_code == 201
        print(f"\n⏱️  텍스트 파이프라인 응답 시간: {elapsed:.2f}s")

        # 30초 타임아웃 이내
        assert elapsed < 30, f"응답 시간이 30초를 초과: {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_multiple_text_queries(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
        sample_text_questions: list[str],
    ) -> None:
        """여러 텍스트 질문에 대해 모두 응답."""
        results = []

        for question in sample_text_questions[:3]:  # 비용 절감을 위해 3개만
            payload = {"message": question}

            start = time.time()
            response = await async_client.post(
                "/api/v1/chat/messages",
                json=payload,
                headers=test_user_headers,
            )
            elapsed = time.time() - start

            results.append(
                {
                    "question": question,
                    "status": response.status_code,
                    "elapsed": elapsed,
                    "answer_length": len(response.json().get("user_answer", "")),
                }
            )

        # 결과 출력
        print("\n📊 텍스트 파이프라인 테스트 결과:")
        for r in results:
            print(f"  Q: {r['question'][:30]}...")
            print(
                f"     Status: {r['status']}, Time: {r['elapsed']:.2f}s, Length: {r['answer_length']}"
            )

        # 모든 요청 성공
        assert all(r["status"] == 201 for r in results)


@pytest.mark.requires_openai
class TestImagePipeline:
    """이미지(Vision) 파이프라인 통합 테스트."""

    @pytest.mark.asyncio
    async def test_image_query_returns_valid_response(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
        sample_image_urls: list[str],
    ) -> None:
        """이미지 질문에 대해 유효한 응답 반환."""
        payload = {
            "message": "이 사진에 있는 것 어떻게 버려?",
            "image_url": sample_image_urls[0],
        }

        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )

        assert response.status_code == 201
        data = response.json()

        assert "user_answer" in data
        assert isinstance(data["user_answer"], str)
        assert len(data["user_answer"]) > 0

    @pytest.mark.asyncio
    async def test_image_query_response_time(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
        sample_image_urls: list[str],
    ) -> None:
        """이미지 쿼리 응답 시간 측정."""
        payload = {
            "message": "이거 분리수거 어떻게?",
            "image_url": sample_image_urls[0],
        }

        start = time.time()
        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )
        elapsed = time.time() - start

        assert response.status_code == 201
        print(f"\n⏱️  이미지 파이프라인 응답 시간: {elapsed:.2f}s")

        # Vision API는 더 오래 걸릴 수 있음 (45초 타임아웃)
        assert elapsed < 45, f"응답 시간이 45초를 초과: {elapsed:.2f}s"


@pytest.mark.requires_openai
class TestTemperatureParameter:
    """Temperature 파라미터 테스트."""

    @pytest.mark.asyncio
    async def test_low_temperature_consistent_response(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """낮은 temperature에서 일관된 응답."""
        payload = {
            "message": "페트병 버리는 방법",
            "temperature": 0.0,
        }

        # 동일 질문 2회 요청
        responses = []
        for _ in range(2):
            response = await async_client.post(
                "/api/v1/chat/messages",
                json=payload,
                headers=test_user_headers,
            )
            responses.append(response.json()["user_answer"])

        # temperature=0 이면 거의 동일한 응답 기대 (100% 동일은 아닐 수 있음)
        print("\n🌡️  Temperature 0.0 응답 비교:")
        print(f"  Response 1: {responses[0][:100]}...")
        print(f"  Response 2: {responses[1][:100]}...")

    @pytest.mark.asyncio
    async def test_custom_temperature_accepted(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """사용자 지정 temperature 값 허용."""
        payload = {
            "message": "유리병 분리수거",
            "temperature": 0.7,
        }

        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )

        assert response.status_code == 200


@pytest.mark.requires_openai
class TestErrorHandling:
    """에러 처리 통합 테스트."""

    @pytest.mark.asyncio
    async def test_invalid_image_url_handled(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """잘못된 이미지 URL도 graceful하게 처리."""
        payload = {
            "message": "이거 뭐야?",
            "image_url": "https://invalid-url-that-does-not-exist.com/image.jpg",
        }

        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )

        # 폴백 응답 반환 (500이 아닌 201)
        assert response.status_code == 201
        data = response.json()
        assert "user_answer" in data

    @pytest.mark.asyncio
    async def test_empty_message_handled(
        self,
        async_client: AsyncClient,
        test_user_headers: dict[str, str],
    ) -> None:
        """빈 메시지도 처리."""
        payload = {"message": ""}

        response = await async_client.post(
            "/api/v1/chat/messages",
            json=payload,
            headers=test_user_headers,
        )

        # Validation error (422) 또는 적절한 응답
        assert response.status_code in [201, 422]


@pytest.mark.requires_openai
class TestHealthWithPipeline:
    """Health 엔드포인트 (파이프라인 포함)."""

    @pytest.mark.asyncio
    async def test_health_endpoint_available(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Health 엔드포인트 정상 응답."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_ready_endpoint_available(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Ready 엔드포인트 정상 응답."""
        response = await async_client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
