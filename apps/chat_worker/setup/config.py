"""Chat Worker Configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Chat Worker 설정."""

    # Environment
    environment: str = "local"  # local, dev, staging, production

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue: str = "chat.process"

    # Redis (기본 - 캐시, Pub/Sub 등)
    redis_url: str = "redis://localhost:6379/0"

    # Redis Streams (이벤트 스트리밍 전용)
    # event-router와 동일한 Redis를 바라봐야 함
    # None이면 redis_url 사용 (로컬 개발용)
    redis_streams_url: str | None = None

    # Checkpoint Redis TTL (분 단위, 기본 24시간)
    # Worker는 Redis에만 checkpoint 저장, syncer가 PostgreSQL로 동기화
    checkpoint_ttl_minutes: int = 1440

    # Checkpoint Read-Through (Worker용, Cold Start Fallback)
    # Redis TTL 만료 세션의 checkpoint를 PostgreSQL에서 읽어 Redis로 promote
    # None이면 Redis-only (PG fallback 비활성화)
    checkpoint_read_postgres_url: str | None = None
    checkpoint_read_pg_pool_min: int = 1  # cold start만 사용, 최소 pool
    checkpoint_read_pg_pool_max: int = 2  # cold start만 사용, 최대 pool

    # Checkpoint Syncer 설정 (checkpoint_syncer 프로세스 전용)
    # Worker에서는 사용하지 않음
    syncer_postgres_url: str | None = None
    syncer_pg_pool_min_size: int = 1
    syncer_pg_pool_max_size: int = 5
    syncer_interval: float = 5.0  # 동기화 주기 (초)
    syncer_batch_size: int = 50  # 배치당 최대 checkpoint 수

    # LLM Provider
    default_provider: Literal["openai", "google"] = "openai"

    # OpenAI
    openai_api_key: str | None = None
    openai_default_model: str = "gpt-5.2"

    # Image Generation (Responses API)
    # 이미지 생성 활성화 여부 (비용 발생, 기본 비활성화)
    enable_image_generation: bool = False
    # Responses API 모델 (프롬프트 최적화 + 오케스트레이션)
    # 기본 LLM과 동일 모델 사용 (설정 단순화)
    image_generation_model: str = "gpt-5.2"
    # 기본 이미지 크기 (1024x1024, 1024x1792, 1792x1024)
    image_generation_default_size: str = "1024x1024"
    # 기본 이미지 품질 (low: ~$0.02, medium: ~$0.07, high: ~$0.19)
    image_generation_default_quality: str = "medium"

    # Images gRPC: 생성된 이미지 S3 업로드 (별도 Pod)
    images_grpc_host: str = "images-api"
    images_grpc_port: int = 50052

    # Gemini
    google_api_key: str | None = None
    gemini_default_model: str = "gemini-3-flash-preview"

    # Assets
    assets_path: str | None = None

    # Web Search (Subagent용)
    # Tavily API 키 (LLM 최적화 검색, 선택적)
    # 없으면 DuckDuckGo 사용 (무료, API 키 불필요)
    tavily_api_key: str | None = None

    # gRPC Clients (Subagent용)
    # Character gRPC: 캐릭터 정보 조회 (별도 Pod)
    character_grpc_host: str = "character-grpc.character.svc.cluster.local"
    character_grpc_port: int = 50051

    # Location gRPC: 주변 센터 검색 (별도 Pod)
    location_grpc_host: str = "location-grpc.location.svc.cluster.local"
    location_grpc_port: int = 50051

    # Kakao Local API (장소 검색)
    # REST API 키 (KakaoMap 설정 ON 필요)
    kakao_rest_api_key: str | None = None
    kakao_api_timeout: float = 10.0

    # 기상청 단기예보 API (날씨 기반 분리배출 팁)
    # 공공데이터포털 인증키 (Decoding 키 권장)
    kma_api_key: str | None = None
    kma_api_timeout: float = 10.0

    # 행정안전부 생활쓰레기배출정보 API (대형폐기물 정보)
    # 공공데이터포털 인증키 (Decoding 키 권장)
    # https://www.data.go.kr/data/15155080/openapi.do
    mois_waste_api_key: str | None = None
    mois_waste_api_timeout: float = 15.0

    # 한국환경공단 폐전자제품 수거함 API (수거함 위치 검색)
    # 공공데이터포털 인증키 (Decoding 키 권장)
    # https://www.data.go.kr/data/15106385/fileData.do
    keco_api_key: str | None = None
    keco_api_timeout: float = 15.0

    # Multi-turn 대화 컨텍스트 압축 (OpenCode 스타일)
    # 동적 설정: context_window - max_output 초과 시 압축 트리거
    enable_summarization: bool = True  # 기본 활성화
    # summarization_model이 설정되면 동적 계산 (권장)
    # - GPT-5.2: 400K - 128K = 272K 트리거, 400K * 15% = 60K 요약
    # - gemini-3-flash-preview: 1M - 64K = 936K 트리거, 1M * 15% = 65K 요약 (max)
    # None이면 아래 수동 설정 사용
    max_tokens_before_summary: int | None = None  # 동적 계산 (None 권장)
    max_summary_tokens: int | None = None  # 동적 계산 (None 권장)
    keep_recent_messages: int | None = None  # 동적 계산 (None 권장)

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "CHAT_WORKER_"
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤."""
    return Settings()
