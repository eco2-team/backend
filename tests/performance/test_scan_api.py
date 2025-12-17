"""
Scan API 성능 테스트 스크립트

Scan API의 AI 파이프라인 성능을 측정합니다.
- Vision Classification (GPT-4o)
- Rule-based Retrieval
- Answer Generation (GPT-4.1)
- Character Reward Matching

사용법:
    # 환경변수 설정
    export ACCESS_TOKEN="your_jwt_token"
    export AUTH_METHOD="cookie"  # cookie 또는 header

    # 일반 테스트 (5명, 10분)
    locust -f tests/performance/test_scan_api.py \
        --host=https://api.dev.growbin.app \
        --users=5 \
        --spawn-rate=1 \
        --run-time=10m \
        --headless

    # Web UI 모드
    locust -f tests/performance/test_scan_api.py \
        --host=https://api.dev.growbin.app
    # http://localhost:8089 접속

주의사항:
    - Scan API는 GPT API를 호출하므로 비용이 발생합니다.
    - 동시 사용자 수를 적절히 조절하세요 (권장: 5~10명).
    - 평균 응답 시간: 8~15초 (GPT 응답 시간 포함)
"""

import os
from typing import ClassVar

from locust import HttpUser, between, task


# 테스트용 이미지 URL 목록
TEST_IMAGES: list[dict] = [
    {
        "url": "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg",
        "description": "재활용 마크가 있는 이미지",
    },
    # 추가 테스트 이미지를 여기에 등록
]


class ScanApiUser(HttpUser):
    """Scan API 성능 테스트 사용자."""

    # 대기 시간 설정 (3~5초) - GPT 호출 고려
    wait_time = between(3, 5)

    # 테스트 이미지 인덱스
    image_index: ClassVar[int] = 0

    def on_start(self):
        """테스트 시작 시 인증 정보 설정."""
        self.access_token = os.getenv("ACCESS_TOKEN", "")
        self.auth_method = os.getenv("AUTH_METHOD", "cookie").lower()

        if not self.access_token:
            raise ValueError("ACCESS_TOKEN 환경변수가 설정되지 않았습니다.")

    def _get_headers(self) -> dict:
        """인증 방식에 따른 헤더 생성."""
        headers = {"Content-Type": "application/json"}

        if self.auth_method == "header":
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:  # cookie
            headers["Cookie"] = f"s_access={self.access_token}"

        return headers

    def _get_test_image(self) -> str:
        """테스트 이미지 URL 반환 (라운드 로빈)."""
        if not TEST_IMAGES:
            return "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"

        url = TEST_IMAGES[ScanApiUser.image_index % len(TEST_IMAGES)]["url"]
        ScanApiUser.image_index += 1
        return url

    @task
    def scan_classify(self):
        """분류 API 호출 - 전체 파이프라인 테스트."""
        headers = self._get_headers()
        payload = {
            "image_url": self._get_test_image(),
            "user_input": "",
        }

        with self.client.post(
            "/api/v1/scan/classify",
            json=payload,
            headers=headers,
            catch_response=True,
            name="/api/v1/scan/classify",
            timeout=60,  # GPT 응답 대기
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure("Unauthorized (401) - 토큰 만료")
            elif response.status_code == 429:
                response.failure("Rate Limit (429) - GPT API 또는 서버 제한")
            elif response.status_code == 504:
                response.failure("Gateway Timeout (504) - GPT 응답 지연")
            elif response.status_code >= 500:
                response.failure(f"Server Error ({response.status_code})")
            else:
                response.failure(f"Unexpected Status ({response.status_code})")


class AggressiveScanUser(HttpUser):
    """공격적인 Scan API 부하 테스트 (스트레스 테스트용).

    주의: GPT API 비용이 급증할 수 있습니다!
    """

    # 짧은 대기 시간 (0.1~0.5초)
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.access_token = os.getenv("ACCESS_TOKEN", "")
        self.auth_method = os.getenv("AUTH_METHOD", "cookie").lower()

        if not self.access_token:
            raise ValueError("ACCESS_TOKEN 환경변수가 설정되지 않았습니다.")

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_method == "header":
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            headers["Cookie"] = f"s_access={self.access_token}"
        return headers

    @task
    def scan_classify_aggressive(self):
        """공격적인 분류 요청."""
        headers = self._get_headers()
        payload = {
            "image_url": "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg",
            "user_input": "",
        }

        with self.client.post(
            "/api/v1/scan/classify",
            json=payload,
            headers=headers,
            catch_response=True,
            name="/api/v1/scan/classify (aggressive)",
            timeout=60,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate Limit (429)")
            elif response.status_code == 504:
                response.failure("Gateway Timeout (504)")
            elif response.status_code >= 500:
                response.failure(f"Server Error ({response.status_code})")
            else:
                response.failure(f"Unexpected Status ({response.status_code})")
