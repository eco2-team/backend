"""
Locust Performance Test for /scan/classify/completion (SSE)

SSE 스트리밍 엔드포인트 성능 측정.
전체 파이프라인(vision → rule → answer → reward) 완료까지 측정.

Usage:
    # 로컬 테스트
    locust -f locustfile_sse.py --host=https://api.dev.growbin.app

    # Headless 모드 (CI용)
    locust -f locustfile_sse.py --host=https://api.dev.growbin.app \
        --headless -u 10 -r 2 -t 60s

Environment Variables:
    ACCESS_COOKIE: 인증 쿠키 값
    TEST_IMAGE_URL: 테스트 이미지 URL (선택)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from locust import HttpUser, between, events, task


class SSEClient:
    """SSE 스트리밍 응답 파서."""

    def __init__(self, response):
        self.response = response
        self.events: list[dict[str, Any]] = []

    def parse(self) -> list[dict[str, Any]]:
        """SSE 이벤트 파싱."""
        buffer = ""
        for chunk in self.response.iter_content(chunk_size=None, decode_unicode=True):
            buffer += chunk
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                event = self._parse_event(event_str)
                if event:
                    self.events.append(event)
        return self.events

    def _parse_event(self, event_str: str) -> dict[str, Any] | None:
        """단일 SSE 이벤트 파싱."""
        lines = event_str.strip().split("\n")
        event_type = None
        data = None

        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = data_str

        if event_type and data:
            return {"event": event_type, "data": data}
        return None


class ScanCompletionUser(HttpUser):
    """SSE 스트리밍 엔드포인트 테스트 사용자."""

    # 요청 간 대기 시간 (SSE는 오래 걸리므로 여유있게)
    wait_time = between(1, 3)

    def on_start(self):
        """테스트 시작 시 설정."""
        self.cookie_val = os.getenv("ACCESS_COOKIE", "")
        self.image_url = os.getenv(
            "TEST_IMAGE_URL",
            "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg",
        )
        self.headers = {
            "Content-Type": "application/json",
            "Cookie": f"s_access={self.cookie_val}",
            "Accept": "text/event-stream",
        }

    @task(weight=10)
    def scan_completion_full(self):
        """전체 파이프라인 SSE 테스트 (vision → rule → answer → reward)."""
        payload = {
            "image_url": self.image_url,
            "user_input": "이 폐기물을 어떻게 분리배출해야 하나요?",
        }

        start_time = time.time()
        stages_completed = []

        try:
            with self.client.post(
                "/api/v1/scan/classify/completion",
                json=payload,
                headers=self.headers,
                stream=True,
                catch_response=True,
                timeout=120,  # SSE는 오래 걸릴 수 있음
            ) as response:
                if response.status_code != 200:
                    response.failure(f"Status {response.status_code}")
                    return

                # SSE 이벤트 파싱
                sse = SSEClient(response)
                events = sse.parse()

                # 스테이지 추적
                for event in events:
                    if event["event"] == "progress":
                        step = event["data"].get("step")
                        status = event["data"].get("status")
                        if step and status == "completed":
                            stages_completed.append(step)

                # 성공 여부 판단
                total_time = (time.time() - start_time) * 1000  # ms
                expected_stages = ["vision", "rule", "answer", "reward"]

                if all(s in stages_completed for s in expected_stages):
                    response.success()
                    # 커스텀 메트릭 기록
                    self._record_stage_metrics(events, total_time)
                else:
                    missing = set(expected_stages) - set(stages_completed)
                    response.failure(f"Missing stages: {missing}")

        except Exception as e:
            self.environment.events.request.fire(
                request_type="POST",
                name="/api/v1/scan/classify/completion",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )

    @task(weight=1)
    def scan_completion_simple(self):
        """간단한 이미지 테스트 (빠른 응답 확인)."""
        payload = {
            "image_url": self.image_url,
            "user_input": "",
        }

        start_time = time.time()

        try:
            with self.client.post(
                "/api/v1/scan/classify/completion",
                json=payload,
                headers=self.headers,
                stream=True,
                catch_response=True,
                timeout=120,
            ) as response:
                if response.status_code == 200:
                    # 첫 이벤트 수신까지 시간 측정
                    first_chunk = next(
                        response.iter_content(chunk_size=1024, decode_unicode=True),
                        None,
                    )
                    if first_chunk:
                        response.success()
                    else:
                        response.failure("No response data")
                else:
                    response.failure(f"Status {response.status_code}")

        except Exception as e:
            self.environment.events.request.fire(
                request_type="POST",
                name="/api/v1/scan/classify/completion (simple)",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                exception=e,
            )

    def _record_stage_metrics(
        self, events: list[dict[str, Any]], total_time: float
    ) -> None:
        """스테이지별 메트릭 기록."""
        stage_times = {}
        for event in events:
            if event["event"] == "progress":
                step = event["data"].get("step")
                status = event["data"].get("status")
                if step and status == "completed":
                    stage_times[step] = event["data"].get("progress", 0)

        # 로그 출력 (디버깅용)
        print(f"[SSE] Total: {total_time:.0f}ms, Stages: {list(stage_times.keys())}")


# 커스텀 통계 출력
@events.quitting.add_listener
def print_stats(environment, **kwargs):
    """테스트 종료 시 통계 출력."""
    stats = environment.stats
    print("\n" + "=" * 60)
    print("SSE Performance Summary")
    print("=" * 60)

    for name, entry in stats.entries.items():
        if entry.num_requests > 0:
            print(f"\n{name}:")
            print(f"  Requests:     {entry.num_requests}")
            print(f"  Failures:     {entry.num_failures}")
            print(f"  Median:       {entry.median_response_time:.0f}ms")
            print(f"  95%:          {entry.get_response_time_percentile(0.95):.0f}ms")
            print(f"  99%:          {entry.get_response_time_percentile(0.99):.0f}ms")
            print(f"  Avg:          {entry.avg_response_time:.0f}ms")
            print(f"  Max:          {entry.max_response_time:.0f}ms")


if __name__ == "__main__":
    import subprocess
    import sys

    # 직접 실행 시 locust 실행
    subprocess.run(
        [
            sys.executable,
            "-m",
            "locust",
            "-f",
            __file__,
            "--host=https://api.dev.growbin.app",
        ]
    )
