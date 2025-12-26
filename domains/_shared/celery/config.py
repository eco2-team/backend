"""
Celery Configuration Module

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
Classic queue 사용 (Celery global QoS 호환)
"""

from functools import lru_cache
from typing import Any

from kombu import Exchange, Queue
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Exchange 정의
default_exchange = Exchange("", type="direct")  # Default exchange
dlx_exchange = Exchange("dlx", type="direct")  # Dead Letter Exchange

# Queue 정의 (DLX 설정 포함 - Topology CR과 완전 동기화)
# Classic queue 사용 - x-queue-type 생략 (기본값)
CELERY_QUEUES = (
    # Default queue
    Queue(
        "celery",
        default_exchange,
        routing_key="celery",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.celery",
            "x-message-ttl": 3600000,  # 1시간
        },
    ),
    # Scan pipeline queues
    Queue(
        "scan.vision",
        default_exchange,
        routing_key="scan.vision",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.scan.vision",
            "x-message-ttl": 3600000,  # 1시간
        },
    ),
    Queue(
        "scan.rule",
        default_exchange,
        routing_key="scan.rule",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.scan.rule",
            "x-message-ttl": 300000,  # 5분
        },
    ),
    Queue(
        "scan.answer",
        default_exchange,
        routing_key="scan.answer",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.scan.answer",
            "x-message-ttl": 3600000,  # 1시간
        },
    ),
    # Reward queues (도메인별 분리)
    Queue(
        "scan.reward",
        default_exchange,
        routing_key="scan.reward",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.scan.reward",
            "x-message-ttl": 3600000,  # 1시간
        },
    ),
    # Character match queue (빠른 응답용)
    Queue(
        "character.match",
        default_exchange,
        routing_key="character.match",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.character.match",
            "x-message-ttl": 30000,  # 30초 (빠른 응답)
        },
    ),
    # Character reward queue (fire & forget, 백그라운드)
    Queue(
        "character.reward",
        default_exchange,
        routing_key="character.reward",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.character.reward",
            "x-message-ttl": 86400000,  # 24시간
        },
    ),
    Queue(
        "my.reward",
        default_exchange,
        routing_key="my.reward",
        queue_arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dlq.my.reward",
            "x-message-ttl": 86400000,  # 24시간
        },
    ),
)


class CelerySettings(BaseSettings):
    """Celery configuration settings."""

    # Broker (RabbitMQ)
    broker_url: str = Field(
        "amqp://guest:guest@localhost:5672/",
        description="RabbitMQ broker URL",
    )

    # Result Backend (RPC for minimal overhead, results via webhook)
    result_backend: str = Field(
        "rpc://",
        description="Result backend URL",
    )

    # Task settings
    task_serializer: str = "json"
    result_serializer: str = "json"
    # pydantic-settings v2에서 list 타입은 JSON 파싱을 먼저 시도하므로
    # str로 선언 후 validator에서 list로 변환
    accept_content: str | list[str] = ["json"]

    @field_validator("accept_content", mode="before")
    @classmethod
    def parse_accept_content(cls, v: Any) -> list[str]:
        """환경변수에서 문자열 또는 쉼표 구분 값을 리스트로 변환."""
        if isinstance(v, list):
            return v
        if v is None or (isinstance(v, str) and not v.strip()):
            # None 또는 빈 문자열인 경우 기본값 반환
            return ["json"]
        if isinstance(v, str):
            v = v.strip()
            # JSON 배열 형태
            if v.startswith("["):
                import json

                return json.loads(v)
            # 쉼표 구분
            return [x.strip() for x in v.split(",") if x.strip()]
        return ["json"]

    timezone: str = "Asia/Seoul"
    enable_utc: bool = True

    # Task execution settings
    task_acks_late: bool = True  # 처리 완료 후 ACK (메시지 손실 방지)
    task_reject_on_worker_lost: bool = True  # Worker 종료 시 재큐잉
    task_time_limit: int = Field(
        300,  # 5분
        description="Hard time limit for task execution (seconds)",
    )
    task_soft_time_limit: int = Field(
        240,  # 4분
        description="Soft time limit for task execution (seconds)",
    )

    # Worker settings
    worker_prefetch_multiplier: int = Field(
        1,  # Fair dispatch (긴 작업에 적합)
        description="Number of tasks to prefetch per worker",
    )
    worker_concurrency: int = Field(
        2,
        description="Number of concurrent worker processes (prefork) or coroutines (asyncio)",
    )
    worker_pool: str = Field(
        "prefork",
        description="Worker pool type: prefork, asyncio, eventlet, gevent",
    )

    # Retry settings
    task_default_retry_delay: int = Field(
        60,  # 1분
        description="Default delay between retries (seconds)",
    )
    task_max_retries: int = Field(
        3,
        description="Maximum number of retries",
    )

    model_config = SettingsConfigDict(
        env_prefix="CELERY_",
        case_sensitive=False,
        extra="ignore",
    )

    def get_celery_config(self) -> dict[str, Any]:
        """Return Celery configuration dictionary."""
        return {
            "broker_url": self.broker_url,
            "result_backend": self.result_backend,
            # Classic queue는 global QoS 지원 - 명시적 설정 불필요
            "broker_transport_options": {
                "confirm_publish": True,
            },
            # Redis 결과 백엔드 연결 풀 튜닝 (연결 누수 방지)
            "result_backend_transport_options": {
                "socket_timeout": 30,  # 소켓 타임아웃 30초
                "socket_connect_timeout": 5,  # 연결 타임아웃 5초
                "retry_on_timeout": True,  # 타임아웃 시 재시도
                "health_check_interval": 30,  # 30초마다 연결 상태 확인
            },
            "task_serializer": self.task_serializer,
            "result_serializer": self.result_serializer,
            "accept_content": self.accept_content,
            "timezone": self.timezone,
            "enable_utc": self.enable_utc,
            "task_acks_late": self.task_acks_late,
            "task_reject_on_worker_lost": self.task_reject_on_worker_lost,
            "task_time_limit": self.task_time_limit,
            "task_soft_time_limit": self.task_soft_time_limit,
            "worker_prefetch_multiplier": self.worker_prefetch_multiplier,
            "worker_concurrency": self.worker_concurrency,
            "task_default_retry_delay": self.task_default_retry_delay,
            # Celery 6.0 deprecation 경고 해소
            "broker_connection_retry_on_startup": True,
            "worker_cancel_long_running_tasks_on_connection_loss": True,
            # Celery Events 활성화 (SSE 실시간 진행상황 + 최종 결과)
            "task_send_sent_event": True,  # task-sent 이벤트 발행
            "worker_send_task_events": True,  # worker에서 task 이벤트 발행
            "task_track_started": True,  # task-started 이벤트 발행 (worker가 task 시작 시)
            "result_extended": True,  # task-succeeded에 result 포함
            # Task routing (도메인별 큐 분리)
            "task_routes": {
                # Scan Chain (scan-worker: AI 처리)
                "scan.vision": {"queue": "scan.vision"},
                "scan.rule": {"queue": "scan.rule"},
                "scan.answer": {"queue": "scan.answer"},
                "scan.reward": {"queue": "scan.reward"},
                # Character match (동기 응답, 빠른 처리)
                "character.match": {"queue": "character.match"},
                # Character reward (fire & forget, 백그라운드)
                "character.save_ownership": {"queue": "character.reward"},
                # My reward (my-worker: my DB 저장)
                "my.save_character": {"queue": "my.reward"},
                # DLQ 재처리 → 각 도메인 worker가 처리
                "dlq.reprocess_scan_vision": {"queue": "scan.vision"},
                "dlq.reprocess_scan_rule": {"queue": "scan.rule"},
                "dlq.reprocess_scan_answer": {"queue": "scan.answer"},
                "dlq.reprocess_scan_reward": {"queue": "scan.reward"},
                "dlq.reprocess_character_reward": {"queue": "character.reward"},
                "dlq.reprocess_my_reward": {"queue": "my.reward"},
            },
            # Queue configuration (DLX 포함하여 명시적 정의)
            "task_queues": CELERY_QUEUES,
            "task_default_queue": "celery",
            "task_default_exchange": "",  # Default exchange (direct routing)
            "task_default_routing_key": "celery",
            # Beat schedule (DLQ 재처리)
            "beat_schedule": {
                "reprocess-dlq-scan-vision": {
                    "task": "dlq.reprocess_scan_vision",
                    "schedule": 300.0,  # 5분마다
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-scan-rule": {
                    "task": "dlq.reprocess_scan_rule",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-scan-answer": {
                    "task": "dlq.reprocess_scan_answer",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-scan-reward": {
                    "task": "dlq.reprocess_scan_reward",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-character-reward": {
                    "task": "dlq.reprocess_character_reward",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-my-reward": {
                    "task": "dlq.reprocess_my_reward",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
            },
        }


@lru_cache
def get_celery_settings() -> CelerySettings:
    """Return cached CelerySettings instance."""
    return CelerySettings()
