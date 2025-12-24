"""
Locust Performance Test - SSE Stage-by-Stage Metrics

각 스테이지(vision, rule, answer, reward)별 응답 시간 측정.
커스텀 메트릭으로 스테이지별 통계 수집.

Usage:
    ACCESS_COOKIE="your-cookie" locust -f locustfile_sse_detailed.py \
        --host=https://api.dev.growbin.app --headless -u 5 -r 1 -t 120s
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from locust import HttpUser, between, events, task


@dataclass
class StageMetrics:
    """스테이지별 메트릭 수집."""

    times: list[float] = field(default_factory=list)

    def add(self, duration_ms: float) -> None:
        self.times.append(duration_ms)

    def percentile(self, p: float) -> float:
        if not self.times:
            return 0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * p)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def avg(self) -> float:
        return sum(self.times) / len(self.times) if self.times else 0

    def count(self) -> int:
        return len(self.times)


# 전역 스테이지 메트릭
STAGE_METRICS: dict[str, StageMetrics] = {
    "vision": StageMetrics(),
    "rule": StageMetrics(),
    "answer": StageMetrics(),
    "reward": StageMetrics(),
    "total": StageMetrics(),
    "ttfb": StageMetrics(),  # Time To First Byte
}


class SSEStageParser:
    """SSE 이벤트 파싱 및 스테이지별 시간 계산."""

    def __init__(self, response, start_time: float):
        self.response = response
        self.start_time = start_time
        self.stage_starts: dict[str, float] = {}
        self.stage_ends: dict[str, float] = {}
        self.first_byte_time: float | None = None
        self.events: list[dict[str, Any]] = []

    def parse(self) -> dict[str, float]:
        """SSE 파싱 및 스테이지별 소요시간 반환."""
        buffer = ""
        for chunk in self.response.iter_content(chunk_size=None, decode_unicode=True):
            if self.first_byte_time is None:
                self.first_byte_time = time.time()

            buffer += chunk
            while "\n\n" in buffer:
                event_str, buffer = buffer.split("\n\n", 1)
                self._process_event(event_str)

        return self._calculate_durations()

    def _process_event(self, event_str: str) -> None:
        """단일 이벤트 처리."""
        lines = event_str.strip().split("\n")
        event_type = None
        data = None

        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

        if event_type == "progress" and data:
            step = data.get("step")
            status = data.get("status")
            now = time.time()

            if step:
                if status == "started":
                    self.stage_starts[step] = now
                elif status == "completed":
                    self.stage_ends[step] = now

    def _calculate_durations(self) -> dict[str, float]:
        """스테이지별 소요시간 계산 (ms)."""
        durations = {}

        for stage in ["vision", "rule", "answer", "reward"]:
            if stage in self.stage_starts and stage in self.stage_ends:
                durations[stage] = (
                    self.stage_ends[stage] - self.stage_starts[stage]
                ) * 1000

        # Total 시간
        if self.stage_ends:
            last_end = max(self.stage_ends.values())
            durations["total"] = (last_end - self.start_time) * 1000

        # TTFB
        if self.first_byte_time:
            durations["ttfb"] = (self.first_byte_time - self.start_time) * 1000

        return durations


class SSEDetailedUser(HttpUser):
    """SSE 스테이지별 상세 측정 사용자."""

    wait_time = between(2, 5)  # SSE 테스트는 여유있게

    def on_start(self):
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

    @task
    def scan_completion_detailed(self):
        """스테이지별 상세 측정."""
        payload = {
            "image_url": self.image_url,
            "user_input": "이 폐기물을 어떻게 분리배출해야 하나요?",
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
                if response.status_code != 200:
                    response.failure(f"Status {response.status_code}")
                    return

                # 스테이지별 파싱
                parser = SSEStageParser(response, start_time)
                durations = parser.parse()

                # 메트릭 수집
                for stage, duration in durations.items():
                    if stage in STAGE_METRICS:
                        STAGE_METRICS[stage].add(duration)

                # 성공 여부 (4개 스테이지 완료)
                required = {"vision", "rule", "answer", "reward"}
                if required.issubset(durations.keys()):
                    response.success()
                    print(
                        f"[OK] vision={durations.get('vision', 0):.0f}ms, "
                        f"rule={durations.get('rule', 0):.0f}ms, "
                        f"answer={durations.get('answer', 0):.0f}ms, "
                        f"reward={durations.get('reward', 0):.0f}ms, "
                        f"total={durations.get('total', 0):.0f}ms"
                    )
                else:
                    missing = required - set(durations.keys())
                    response.failure(f"Missing: {missing}")

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            self.environment.events.request.fire(
                request_type="POST",
                name="/api/v1/scan/classify/completion",
                response_time=elapsed,
                response_length=0,
                exception=e,
            )


@events.quitting.add_listener
def print_stage_stats(environment, **kwargs):
    """테스트 종료 시 스테이지별 통계 출력."""
    print("\n" + "=" * 70)
    print("SSE Stage-by-Stage Performance Summary")
    print("=" * 70)
    print(f"{'Stage':<12} {'Count':>8} {'Avg':>10} {'p50':>10} {'p95':>10} {'p99':>10}")
    print("-" * 70)

    for stage in ["ttfb", "vision", "rule", "answer", "reward", "total"]:
        m = STAGE_METRICS[stage]
        if m.count() > 0:
            print(
                f"{stage:<12} {m.count():>8} "
                f"{m.avg():>9.0f}ms "
                f"{m.percentile(0.5):>9.0f}ms "
                f"{m.percentile(0.95):>9.0f}ms "
                f"{m.percentile(0.99):>9.0f}ms"
            )

    print("=" * 70)

    # Breakdown 비율
    if STAGE_METRICS["total"].count() > 0:
        total_avg = STAGE_METRICS["total"].avg()
        print("\nTime Breakdown (% of total):")
        for stage in ["vision", "rule", "answer", "reward"]:
            m = STAGE_METRICS[stage]
            if m.count() > 0:
                pct = (m.avg() / total_avg) * 100 if total_avg else 0
                bar = "█" * int(pct / 2)
                print(f"  {stage:<10} {pct:5.1f}% {bar}")


if __name__ == "__main__":
    import subprocess
    import sys

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
