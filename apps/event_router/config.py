"""Event Router 설정.

환경 변수:
- REDIS_STREAMS_URL: Redis Streams 연결 URL (XREADGROUP/XACK + State KV)
- REDIS_PUBSUB_URL: Redis Pub/Sub 연결 URL (PUBLISH only)
- CONSUMER_GROUP: Consumer Group 이름 (default: eventrouter)
- POD_NAME: Pod 이름 (Consumer 이름으로 사용)
- SHARD_COUNT: scan 도메인 Shard 수 (default: 4)
- CHAT_SHARD_COUNT: chat 도메인 Shard 수 (default: 4)
- LOG_LEVEL: 로그 레벨 (default: INFO)

Redis 역할 분리:
- Streams Redis (내구성): XREADGROUP, XACK, State KV ({domain}:state:{job_id})
- Pub/Sub Redis (실시간): PUBLISH only (sse:events:{job_id})

State KV는 Streams Redis에 둬야 함:
- 복구/재접속 시 현재 상태 조회 필요 (Source of Truth)
- Pub/Sub는 저장 안됨 → State로 부적합

멀티 도메인 지원:
- scan:events → scan:state
- chat:events → chat:state (LangGraph 체크포인팅은 별도 PostgreSQL)

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

    # Redis Streams + State KV (XREADGROUP/XACK + SETEX)
    # State는 내구성 있는 저장소에 두어야 함
    # 기본값: 로컬 개발용, K8s에서는 deployment.yaml에서 오버라이드
    redis_streams_url: str = "redis://localhost:6379/0"

    # Redis Pub/Sub (PUBLISH only - 실시간 전달용)
    # 기본값: 로컬 개발용, K8s에서는 deployment.yaml에서 오버라이드
    redis_pubsub_url: str = "redis://localhost:6379/1"

    # Consumer Group 설정
    consumer_group: str = "eventrouter"
    consumer_name: str = os.environ.get("POD_NAME", "event-router-0")

    # Shard 설정
    shard_count: int = 4

    # 멀티 도메인 스트림 (쉼표 구분 문자열 → 리스트로 파싱)
    # 예: "scan:events,chat:events"
    stream_prefixes_str: str = "scan:events,chat:events"

    # 도메인별 Shard 수 (기본: 모두 동일)
    # scan과 동일하게 4개 shard 사용
    chat_shard_count: int = 4

    @property
    def stream_prefixes(self) -> list[str]:
        """스트림 prefix 리스트."""
        return [p.strip() for p in self.stream_prefixes_str.split(",") if p.strip()]

    def get_shard_count(self, prefix: str) -> int:
        """도메인별 shard 수 반환."""
        if prefix == "chat:events":
            return self.chat_shard_count
        return self.shard_count

    # Consumer 설정
    xread_block_ms: int = 5000  # XREADGROUP 블로킹 시간
    xread_count: int = 100  # 한 번에 읽을 최대 메시지 수
    batch_size: int = 50  # 배치 처리 크기

    # Reclaimer 설정
    reclaim_min_idle_ms: int = 300000  # 5분 이상 Pending인 메시지 재할당
    reclaim_interval_seconds: int = 60  # Reclaim 체크 주기

    # Pub/Sub 설정
    pubsub_channel_prefix: str = "sse:events"

    # State 설정 (도메인별 자동 결정: scan:events → scan:state)
    router_published_prefix: str = "router:published"
    state_ttl: int = 3600  # 1시간
    published_ttl: int = 7200  # 2시간

    def get_state_prefix(self, stream_prefix: str) -> str:
        """스트림 prefix에서 state prefix 유도.

        scan:events → scan:state
        chat:events → chat:state
        """
        return stream_prefix.replace(":events", ":state")

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
