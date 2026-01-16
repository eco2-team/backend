"""Chat API E2E Tests.

전체 플로우 테스트:
1. POST /chat - 채팅 제출
2. GET /chat/{job_id}/events - SSE 스트리밍
3. POST /chat/{job_id}/input - Human-in-the-Loop

Usage:
    pytest e2e-tests/performance/test_chat_api.py -v
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx
import pytest

BASE_URL = os.environ.get("CHAT_API_URL", "http://localhost:8000")
SSE_GATEWAY_URL = os.environ.get("SSE_GATEWAY_URL", "http://localhost:8001")


@pytest.fixture
def headers():
    """테스트용 헤더."""
    return {
        "X-User-ID": "e2e-test-user",
        "X-User-Role": "user",
        "Content-Type": "application/json",
    }


class TestChatSubmit:
    """Chat 제출 테스트."""

    @pytest.mark.asyncio
    async def test_submit_text_message(self, headers):
        """텍스트 메시지 제출."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-session-{int(time.time())}",
                    "message": "페트병은 어떻게 버리나요?",
                },
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "stream_url" in data
        assert data["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submit_with_image(self, headers):
        """이미지 포함 메시지 제출."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-img-{int(time.time())}",
                    "message": "이 쓰레기 어떻게 분류해요?",
                    "image_url": "https://example.com/test.jpg",
                },
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data

    @pytest.mark.asyncio
    async def test_submit_with_location(self, headers):
        """위치 포함 메시지 제출."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-loc-{int(time.time())}",
                    "message": "근처 재활용센터 알려줘",
                    "user_location": {
                        "latitude": 37.5665,
                        "longitude": 126.9780,
                    },
                },
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data

    @pytest.mark.asyncio
    async def test_submit_empty_message_fails(self, headers):
        """빈 메시지 제출 실패."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": "e2e-empty",
                    "message": "",
                },
                headers=headers,
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_submit_without_auth_fails(self):
        """인증 없이 제출 실패."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": "e2e-noauth",
                    "message": "테스트",
                },
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 401


class TestSSEStreaming:
    """SSE 스트리밍 테스트."""

    @pytest.mark.asyncio
    async def test_sse_connection(self, headers):
        """SSE 연결 테스트."""
        # 1. 채팅 제출
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            submit_response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-sse-{int(time.time())}",
                    "message": "페트병 분리배출",
                },
                headers=headers,
            )

        assert submit_response.status_code == 200
        job_id = submit_response.json()["job_id"]

        # 2. SSE 연결
        events = []
        async with httpx.AsyncClient(
            base_url=SSE_GATEWAY_URL, timeout=60.0
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/chat/{job_id}/events",
                    headers={**headers, "Accept": "text/event-stream"},
                ) as response:
                    assert response.status_code == 200

                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            events.append(line[5:].strip())
                            # 최대 10개 이벤트만 수집
                            if len(events) >= 10:
                                break
            except httpx.ReadTimeout:
                pass  # 타임아웃은 정상

        # 이벤트 수신 확인
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_sse_event_format(self, headers):
        """SSE 이벤트 형식 검증."""
        # 1. 채팅 제출
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            submit_response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-format-{int(time.time())}",
                    "message": "테스트 메시지",
                },
                headers=headers,
            )

        job_id = submit_response.json()["job_id"]

        # 2. SSE 이벤트 수집
        events = []
        async with httpx.AsyncClient(
            base_url=SSE_GATEWAY_URL, timeout=60.0
        ) as client:
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/chat/{job_id}/events",
                    headers={**headers, "Accept": "text/event-stream"},
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            import json
                            event_data = json.loads(line[5:].strip())
                            events.append(event_data)
                            if len(events) >= 5:
                                break
            except (httpx.ReadTimeout, Exception):
                pass

        # 이벤트 형식 검증
        for event in events:
            # 기본 필드 확인
            assert "stage" in event or "type" in event


class TestHumanInTheLoop:
    """Human-in-the-Loop 테스트."""

    @pytest.mark.asyncio
    async def test_submit_user_input(self, headers):
        """추가 입력 제출."""
        # 1. 채팅 제출 (위치 없이)
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            submit_response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-hitl-{int(time.time())}",
                    "message": "근처 재활용센터",
                    # user_location 없음 → needs_input 발생
                },
                headers=headers,
            )

        job_id = submit_response.json()["job_id"]

        # 2. 추가 입력 제출
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            input_response = await client.post(
                f"/api/v1/chat/{job_id}/input",
                json={
                    "type": "location",
                    "data": {
                        "latitude": 37.5665,
                        "longitude": 126.9780,
                    },
                },
                headers=headers,
            )

        assert input_response.status_code == 200
        data = input_response.json()
        assert data["status"] == "received"
        assert data["job_id"] == job_id

    @pytest.mark.asyncio
    async def test_submit_cancel_input(self, headers):
        """취소 입력 제출."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # 먼저 채팅 제출
            submit_response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-cancel-{int(time.time())}",
                    "message": "재활용센터",
                },
                headers=headers,
            )
            job_id = submit_response.json()["job_id"]

            # 취소 입력
            cancel_response = await client.post(
                f"/api/v1/chat/{job_id}/input",
                json={"type": "cancel"},
                headers=headers,
            )

        assert cancel_response.status_code == 200


class TestMultiTurnConversation:
    """멀티턴 대화 테스트."""

    @pytest.mark.asyncio
    async def test_same_session_multiple_messages(self, headers):
        """같은 세션에서 여러 메시지."""
        session_id = f"e2e-multiturn-{int(time.time())}"

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # 첫 번째 메시지
            response1 = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": session_id,
                    "message": "페트병 버리는 방법",
                },
                headers=headers,
            )
            assert response1.status_code == 200

            # 두 번째 메시지 (같은 세션)
            response2 = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": session_id,
                    "message": "그럼 뚜껑은요?",
                },
                headers=headers,
            )
            assert response2.status_code == 200

            # 세 번째 메시지 (같은 세션)
            response3 = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": session_id,
                    "message": "감사합니다",
                },
                headers=headers,
            )
            assert response3.status_code == 200

        # 모든 요청이 같은 세션 ID를 가져야 함
        assert response1.json()["session_id"] == session_id
        assert response2.json()["session_id"] == session_id
        assert response3.json()["session_id"] == session_id

        # job_id는 각각 달라야 함
        job_ids = {
            response1.json()["job_id"],
            response2.json()["job_id"],
            response3.json()["job_id"],
        }
        assert len(job_ids) == 3


class TestChatPerformance:
    """성능 테스트."""

    @pytest.mark.asyncio
    async def test_concurrent_submissions(self, headers):
        """동시 제출 테스트."""

        async def submit_chat(message: str) -> dict[str, Any]:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
                response = await client.post(
                    "/api/v1/chat",
                    json={
                        "session_id": f"e2e-concurrent-{int(time.time() * 1000)}",
                        "message": message,
                    },
                    headers=headers,
                )
                return {
                    "status": response.status_code,
                    "data": response.json() if response.status_code == 200 else None,
                }

        messages = [
            "페트병 분리배출",
            "음식물쓰레기 처리",
            "건전지 버리기",
            "플라스틱 재활용",
            "종이컵 분리수거",
        ]

        # 동시 실행
        results = await asyncio.gather(*[submit_chat(msg) for msg in messages])

        # 모든 요청 성공 확인
        success_count = sum(1 for r in results if r["status"] == 200)
        assert success_count == len(messages)

    @pytest.mark.asyncio
    async def test_response_time(self, headers):
        """응답 시간 측정."""
        start_time = time.time()

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/api/v1/chat",
                json={
                    "session_id": f"e2e-perf-{int(time.time())}",
                    "message": "테스트",
                },
                headers=headers,
            )

        elapsed = time.time() - start_time

        assert response.status_code == 200
        # 제출은 5초 이내에 완료되어야 함
        assert elapsed < 5.0
