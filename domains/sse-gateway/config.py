"""SSE Gateway 설정.

환경 변수:
- REDIS_STREAMS_URL: Redis Streams 연결 URL
- REDIS_CACHE_URL: Redis Cache 연결 URL (KV 스냅샷용)
- POD_NAME: StatefulSet Pod 이름 (예: sse-gateway-0)
- SSE_SHARD_COUNT: 전체 shard 수 (default: 4)
- OTEL_EXPORTER_OTLP_ENDPOINT: OTEL Collector 엔드포인트
- LOG_LEVEL: 로그 레벨 (default: INFO)

B안 샤딩 아키텍처 (StatefulSet 기반):
- 스트림을 N개로 샤딩: scan:events:0 ~ scan:events:N-1
- Pod Index = Shard ID (sse-gateway-0 → shard 0)
- Istio Consistent Hash 라우팅으로 동일 job_id는 동일 Pod로

참조: docs/blogs/async/32-sse-sharding-troubleshooting.md
"""

import os
import re
from functools import lru_cache

from pydantic_settings import BaseSettings


def get_pod_index() -> int:
    """POD_NAME에서 StatefulSet 인덱스 추출.

    StatefulSet Pod 이름 형식: {name}-{index}
    예: sse-gateway-2 → 2

    Returns:
        Pod 인덱스 (0-based). 추출 실패 시 0 반환.
    """
    pod_name = os.environ.get("POD_NAME", "sse-gateway-0")
    match = re.search(r"-(\d+)$", pod_name)
    return int(match.group(1)) if match else 0


class Settings(BaseSettings):
    """SSE Gateway 설정."""

    # Service Info
    service_name: str = "sse-gateway"
    service_version: str = "1.0.0"
    environment: str = "development"

    # Redis Streams (SSE 이벤트 소스)
    redis_streams_url: str = "redis://rfr-streams-redis.redis.svc.cluster.local:6379/0"

    # Redis Cache (KV 스냅샷용 - 재접속 시 상태 복구)
    redis_cache_url: str = "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 샤딩 설정 (B안 - StatefulSet 기반)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # shard = hash(job_id) % shard_count
    # Pod Index = Shard ID (sse-gateway-0 → shard 0)
    sse_shard_count: int = 4  # 전체 shard 수 (권장: Pod 수와 동일)

    @property
    def sse_shard_id(self) -> int:
        """이 Pod가 담당하는 shard ID (POD_NAME에서 동적 추출)."""
        return get_pod_index()

    # SSE 설정
    sse_keepalive_interval: float = 15.0  # keepalive 주기 (초)
    sse_max_wait_seconds: int = 300  # 최대 대기 시간 (5분)
    sse_queue_maxsize: int = 100  # 클라이언트별 Queue 최대 크기

    # Redis Consumer 설정
    consumer_xread_block_ms: int = 5000  # XREAD 블로킹 시간
    consumer_xread_count: int = 100  # 한 번에 읽을 최대 메시지 수

    # 로깅
    log_level: str = "INFO"

    # OTEL (샘플링 낮춤 - SSE 경로)
    otel_enabled: bool = True
    otel_sample_rate: float = 0.1  # 10% 샘플링

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()


def get_shard_for_job(job_id: str, shard_count: int | None = None) -> int:
    """job_id에 대한 shard 계산.

    Args:
        job_id: Celery task ID (UUID)
        shard_count: 전체 shard 수 (None이면 설정값 사용)

    Returns:
        shard ID (0-based)
    """
    if shard_count is None:
        shard_count = get_settings().sse_shard_count
    return hash(job_id) % shard_count


def get_sharded_stream_key(job_id: str, shard_count: int | None = None) -> str:
    """job_id에 해당하는 sharded stream key 반환.

    Args:
        job_id: Celery task ID (UUID)
        shard_count: 전체 shard 수

    Returns:
        Stream key (예: "scan:events:2")
    """
    shard = get_shard_for_job(job_id, shard_count)
    return f"scan:events:{shard}"
