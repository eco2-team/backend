"""Submit Classification Command - 분류 작업 제출."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from scan.application.classify.ports import EventPublisher, IdempotencyCache
from scan.domain.entities import ScanTask
from scan.domain.enums import PipelineStage

if TYPE_CHECKING:
    from celery import Celery

logger = logging.getLogger(__name__)

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

        pipeline = chain(
            self._celery_app.signature(
                "scan.vision",
                args=[job_id, request.user_id, request.image_url, user_input],
                kwargs={"model": model},
                queue="scan.vision",
            ),
            self._celery_app.signature("scan.rule", queue="scan.rule"),
            self._celery_app.signature("scan.answer", queue="scan.answer"),
            self._celery_app.signature("scan.reward", queue="scan.reward"),
        )
        pipeline.apply_async(task_id=job_id)

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
