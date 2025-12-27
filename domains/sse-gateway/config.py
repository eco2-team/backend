"""SSE Gateway 설정.

환경 변수:
- REDIS_STREAMS_URL: Redis 연결 URL (Pub/Sub + State KV)
- OTEL_EXPORTER_OTLP_ENDPOINT: OTEL Collector 엔드포인트
- LOG_LEVEL: 로그 레벨 (default: INFO)

Event Router + Pub/Sub 아키텍처:
- SSE-Gateway는 Redis Pub/Sub를 통해 이벤트 수신
- 어느 Pod에 연결되든 동일한 이벤트를 받을 수 있음
- State KV에서 재접속 시 상태 복구

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """SSE Gateway 설정."""

    # Service Info
    service_name: str = "sse-gateway"
    service_version: str = "1.0.0"
    environment: str = "development"

    # Redis Pub/Sub + State KV
    # Event Router가 발행한 이벤트를 구독하고 State를 조회
    redis_pubsub_url: str = "redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0"

    # Redis Cache (하위 호환성 유지)
    redis_cache_url: str = "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0"

    # SSE 설정
    sse_keepalive_interval: float = 15.0  # keepalive 주기 (초)
    sse_max_wait_seconds: int = 300  # 최대 대기 시간 (5분)
    sse_queue_maxsize: int = 100  # 클라이언트별 Queue 최대 크기

    # Pub/Sub 설정
    pubsub_channel_prefix: str = "sse:events"  # 채널 접두사 (sse:events:{job_id})
    state_key_prefix: str = "scan:state"  # State KV 접두사 (scan:state:{job_id})
    state_timeout_seconds: int = 30  # State 재조회 타임아웃 (무소식 시)

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
