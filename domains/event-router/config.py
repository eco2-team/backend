"""Event Router 설정.

환경 변수:
- REDIS_STREAMS_URL: Redis Streams 연결 URL (XREADGROUP/XACK)
- REDIS_PUBSUB_URL: Redis Pub/Sub 연결 URL (PUBLISH + State KV)
- CONSUMER_GROUP: Consumer Group 이름 (default: eventrouter)
- POD_NAME: Pod 이름 (Consumer 이름으로 사용)
- SSE_SHARD_COUNT: Shard 수 (default: 4)
- LOG_LEVEL: 로그 레벨 (default: INFO)

Event Router 역할:
- Redis Streams에서 XREADGROUP으로 이벤트 소비
- State KV 갱신 (seq 비교)
- Redis Pub/Sub로 발행
- XACK로 메시지 확인
- XAUTOCLAIM으로 장애 복구

참조: docs/blogs/async/34-sse-HA-architecture.md
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Event Router 설정."""

    # Service Info
    service_name: str = "event-router"
    service_version: str = "1.0.0"
    environment: str = "development"

    # Redis Streams (XREADGROUP/XACK)
    redis_streams_url: str = "redis://rfr-streams-redis.redis.svc.cluster.local:6379/0"

    # Redis Pub/Sub + State KV (PUBLISH/SETEX)
    redis_pubsub_url: str = "redis://rfr-pubsub-redis.redis.svc.cluster.local:6379/0"

    # Consumer Group 설정
    consumer_group: str = "eventrouter"
    consumer_name: str = os.environ.get("POD_NAME", "event-router-0")

    # Shard 설정
    shard_count: int = 4
    stream_prefix: str = "scan:events"

    # Consumer 설정
    xread_block_ms: int = 5000  # XREADGROUP 블로킹 시간
    xread_count: int = 100  # 한 번에 읽을 최대 메시지 수
    batch_size: int = 50  # 배치 처리 크기

    # Reclaimer 설정
    reclaim_min_idle_ms: int = 300000  # 5분 이상 Pending인 메시지 재할당
    reclaim_interval_seconds: int = 60  # Reclaim 체크 주기

    # Pub/Sub 설정
    pubsub_channel_prefix: str = "sse:events"

    # State 설정
    state_key_prefix: str = "scan:state"
    router_published_prefix: str = "router:published"
    state_ttl: int = 3600  # 1시간
    published_ttl: int = 7200  # 2시간

    # 로깅
    log_level: str = "INFO"

    # OTEL
    otel_enabled: bool = True
    otel_sample_rate: float = 0.1

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
