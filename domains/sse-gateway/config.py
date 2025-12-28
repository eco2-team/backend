"""SSE Gateway 설정.

환경 변수:
- REDIS_STREAMS_URL: Redis Streams + State KV (내구성 저장소)
- REDIS_PUBSUB_URL: Redis Pub/Sub (실시간 구독)
- OTEL_EXPORTER_OTLP_ENDPOINT: OTEL Collector 엔드포인트
- LOG_LEVEL: 로그 레벨 (default: INFO)

Redis 역할 분리:
- Streams Redis: State KV 조회 (scan:state:{job_id}) - 복구/재접속용
- Pub/Sub Redis: 실시간 이벤트 구독 (sse:events:{job_id})

State는 내구성 저장소에 있어야 복구/재접속 시 사용 가능

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

    # Redis Streams + State KV (내구성 저장소)
    # State 조회용 (복구/재접속 시 현재 상태)
    # 기본값: 로컬 개발용, K8s에서는 deployment.yaml에서 오버라이드
    redis_streams_url: str = "redis://localhost:6379/0"

    # Redis Pub/Sub (실시간 구독)
    # Event Router가 발행한 이벤트 수신
    # 기본값: 로컬 개발용, K8s에서는 deployment.yaml에서 오버라이드
    redis_pubsub_url: str = "redis://localhost:6379/1"

    # Redis Cache (하위 호환성 유지)
    # 기본값: 로컬 개발용, K8s에서는 deployment.yaml에서 오버라이드
    redis_cache_url: str = "redis://localhost:6379/2"

    # SSE 설정
    sse_keepalive_interval: float = 15.0  # keepalive 주기 (초)
    sse_max_wait_seconds: int = 300  # 최대 대기 시간 (5분)
    sse_queue_maxsize: int = 100  # 클라이언트별 Queue 최대 크기

    # Pub/Sub 설정
    pubsub_channel_prefix: str = "sse:events"  # 채널 접두사 (sse:events:{job_id})
    state_key_prefix: str = "scan:state"  # State KV 접두사 (scan:state:{job_id})
    state_timeout_seconds: int = (
        5  # State 재조회 타임아웃 (무소식 시) - 짧게 설정하여 누락 이벤트 빠른 복구
    )

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
