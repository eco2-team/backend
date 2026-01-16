"""Submit Classification Command - 분류 작업 제출.

분산 트레이싱 통합:
- API 요청의 trace context를 Celery headers로 전파
- Worker가 headers에서 trace context를 복원하여 child span 생성
- Jaeger/Kiali에서 API → Worker 흐름 추적 가능
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from scan.application.classify.ports import EventPublisher, IdempotencyCache
from scan.domain.entities import ScanTask
from scan.domain.enums import PipelineStage

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)

# OpenTelemetry 활성화 여부
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"

# Celery headers에서 사용하는 trace context 키
TRACEPARENT_HEADER = "traceparent"

# Idempotency key TTL (1시간)
IDEMPOTENCY_TTL = 3600


@dataclass
class SubmitClassificationRequest:
    """분류 제출 요청 DTO."""

    user_id: str
    image_url: str
    user_input: str | None = None
    idempotency_key: str | None = None
    model: str = "gpt-5.2"


@dataclass
class SubmitClassificationResponse:
    """분류 제출 응답 DTO."""

    job_id: str
    stream_url: str
    result_url: str
    status: str


class SubmitClassificationCommand:
    """분류 작업 제출 Command.

    Celery Chain을 발행하고 job_id를 반환합니다.
    X-Idempotency-Key로 중복 제출을 방지합니다.
    """

    def __init__(
        self,
        event_publisher: EventPublisher,
        idempotency_cache: IdempotencyCache,
        celery_app: "Celery",
        idempotency_ttl: int = IDEMPOTENCY_TTL,
    ):
        """초기화.

        Args:
            event_publisher: Redis Streams 이벤트 발행기
            idempotency_cache: 멱등성 캐시
            celery_app: Celery 앱 인스턴스
            idempotency_ttl: 멱등성 키 TTL (초)
        """
        self._event_publisher = event_publisher
        self._idempotency_cache = idempotency_cache
        self._celery_app = celery_app
        self._idempotency_ttl = idempotency_ttl

    def _get_trace_headers(self) -> dict[str, str]:
        """현재 trace context를 Celery headers로 추출.

        OpenTelemetry의 현재 span에서 trace context를 추출하여
        Celery task에 전파할 headers 딕셔너리를 반환.

        Worker의 BaseTask.before_start()에서 이 headers를 읽어
        trace context를 복원하고 child span을 생성.

        Returns:
            trace context headers (빈 딕셔너리 if OTEL 비활성화)
        """
        if not OTEL_ENABLED:
            return {}

        try:
            from opentelemetry import trace
            from opentelemetry.trace import format_trace_id, format_span_id

            current_span = trace.get_current_span()
            span_context = current_span.get_span_context()

            if span_context.is_valid:
                trace_id = format_trace_id(span_context.trace_id)
                span_id = format_span_id(span_context.span_id)
                trace_flags = f"{span_context.trace_flags:02x}"
                traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"
                return {TRACEPARENT_HEADER: traceparent}
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Failed to get trace context: {e}")

        return {}

    async def execute(
        self,
        request: SubmitClassificationRequest,
    ) -> SubmitClassificationResponse:
        """분류 작업 제출 실행.

        Args:
            request: 제출 요청

        Returns:
            제출 응답 (job_id, stream_url, result_url)
        """
        from celery import chain

        # 1. Idempotency 체크 (중복 제출 방지)
        if request.idempotency_key:
            cached = await self._idempotency_cache.get(request.idempotency_key)
            if cached:
                logger.info(
                    "scan_idempotent_hit",
                    extra={"idempotency_key": request.idempotency_key},
                )
                return SubmitClassificationResponse(
                    job_id=cached["job_id"],
                    stream_url=cached["stream_url"],
                    result_url=cached["result_url"],
                    status=cached["status"],
                )

        # 2. Task 생성
        job_id = str(uuid4())
        task = ScanTask(
            task_id=job_id,
            user_id=request.user_id,
            image_url=request.image_url,
            user_input=request.user_input,
        )

        # 3. Redis Streams: queued 이벤트 발행
        self._event_publisher.publish_stage_event(
            job_id=job_id,
            stage=PipelineStage.QUEUED.value,
            status="started",
            progress=PipelineStage.QUEUED.progress,
        )

        # 4. Celery Chain 발행
        user_input = request.user_input or "이 폐기물을 어떻게 분리배출해야 하나요?"
        model = request.model

        # ⚠️ routing_key만 사용 (queue 선언 X) - Topology CR과 arguments 충돌 방지
        pipeline = chain(
            self._celery_app.signature(
                "scan.vision",
                args=[job_id, request.user_id, request.image_url, user_input],
                kwargs={"model": model},
                options={"routing_key": "scan.vision"},
            ),
            self._celery_app.signature("scan.rule", options={"routing_key": "scan.rule"}),
            self._celery_app.signature("scan.answer", options={"routing_key": "scan.answer"}),
            self._celery_app.signature("scan.reward", options={"routing_key": "scan.reward"}),
        )

        # Trace context를 Celery headers로 전파
        celery_headers = self._get_trace_headers()
        pipeline.apply_async(task_id=job_id, headers=celery_headers)

        logger.info(
            "scan_submitted",
            extra={
                "job_id": job_id,
                "user_id": request.user_id,
                "image_url": request.image_url,
                "model": model,
                "idempotency_key": request.idempotency_key,
            },
        )

        # 5. 응답 생성
        response = SubmitClassificationResponse(
            job_id=job_id,
            stream_url=f"/api/v1/scan/{job_id}/events",
            result_url=f"/api/v1/scan/{job_id}/result",
            status=task.status.value,
        )

        # 6. Idempotency 캐시 저장
        if request.idempotency_key:
            await self._idempotency_cache.set(
                key=request.idempotency_key,
                response={
                    "job_id": response.job_id,
                    "stream_url": response.stream_url,
                    "result_url": response.result_url,
                    "status": response.status,
                },
                ttl=self._idempotency_ttl,
            )
            logger.debug(
                "idempotency_key_saved",
                extra={
                    "idempotency_key": request.idempotency_key,
                    "job_id": job_id,
                },
            )

        return response
