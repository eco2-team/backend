import os
from locust import HttpUser, task, between

class ScanUser(HttpUser):
    # 사용자 간 대기 시간 (0.1~0.5초 랜덤 딜레이) -> 매우 공격적인 부하
    wait_time = between(0.1, 0.5)

    @task
    def scan_classify(self):
        # 테스트용 이미지 (재활용 마크가 있는 이미지)
        payload = {
            "image_url": "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg",
            "user_input": ""
        }

        # 인증 쿠키 설정 (환경변수에서 로드)
        cookie_val = os.getenv("ACCESS_COOKIE", "")
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"s_access={cookie_val}"
        }

        # API 호출 및 결과 확인
        with self.client.post("/api/v1/scan/classify", json=payload, headers=headers, catch_response=True) as response:
            # 200 OK면 성공
            if response.status_code == 200:
                response.success()
            # 429 (Rate Limit)는 실패지만 서버 다운은 아님
            elif response.status_code == 429:
                response.failure("Rate Limit (429)")
            # 5xx 에러는 심각한 실패
            elif response.status_code >= 500:
                response.failure(f"Server Error ({response.status_code})")
            else:
                response.failure(f"Unexpected Status ({response.status_code})")
