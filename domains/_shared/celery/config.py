"""
Celery Configuration Module

환경변수 기반 동적 설정 - 배포 환경별로 변경됨
"""

from functools import lru_cache
from typing import Any

from kombu import Exchange, Queue
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Exchange 정의
default_exchange = Exchange("", type="direct")  # Default exchange
dlx_exchange = Exchange("dlx", type="direct")  # Dead Letter Exchange

# Queue 정의 (DLX 설정 포함)
CELERY_QUEUES = (
    # Default queue
    Queue("celery", default_exchange, routing_key="celery"),
    # Scan pipeline queues
    Queue(
        "scan.vision",
        default_exchange,
        routing_key="scan.vision",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
    ),
    Queue(
        "scan.rule",
        default_exchange,
        routing_key="scan.rule",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
    ),
    Queue(
        "scan.answer",
        default_exchange,
        routing_key="scan.answer",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
    ),
    # Reward/Character queues
    Queue(
        "reward.character",
        default_exchange,
        routing_key="reward.character",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
    ),
    Queue(
        "reward.persist",
        default_exchange,
        routing_key="reward.persist",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
    ),
    Queue(
        "my.sync",
        default_exchange,
        routing_key="my.sync",
        queue_arguments={"x-dead-letter-exchange": "dlx"},
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
        description="Number of concurrent worker processes",
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
            # Celery Events 활성화 (SSE 실시간 진행상황 + 최종 결과)
            "task_send_sent_event": True,  # task-sent 이벤트 발행
            "worker_send_task_events": True,  # worker에서 task 이벤트 발행
            "result_extended": True,  # task-succeeded에 result 포함
            # Task routing (Phase 2+3: 4단계 Chain + Worker 분리)
            "task_routes": {
                # Scan Chain (scan-worker: AI 처리)
                "scan.vision": {"queue": "scan.vision"},
                "scan.rule": {"queue": "scan.rule"},
                "scan.answer": {"queue": "scan.answer"},
                # Reward (character-worker: 판정 + DB 저장)
                "scan.reward": {"queue": "reward.character"},  # 판정만 (빠른 응답)
                "character.persist_reward": {"queue": "reward.persist"},  # dispatcher
                "character.save_ownership": {"queue": "reward.persist"},  # character DB
                "character.save_my_character": {"queue": "my.sync"},  # my DB (직접)
                "reward.*": {"queue": "reward.character"},  # Legacy 호환
                "character.sync_to_my": {"queue": "my.sync"},  # deprecated (gRPC)
                # DLQ 재처리
                "dlq.*": {"queue": "celery"},
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
                "reprocess-dlq-reward": {
                    "task": "dlq.reprocess_reward",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
                "reprocess-dlq-my-sync": {
                    "task": "dlq.reprocess_my_sync",
                    "schedule": 300.0,
                    "kwargs": {"max_messages": 10},
                },
            },
        }


@lru_cache
def get_celery_settings() -> CelerySettings:
    """Return cached CelerySettings instance."""
    return CelerySettings()
