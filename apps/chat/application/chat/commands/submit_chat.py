"""Submit Chat Command - 채팅 작업 제출.

API의 유일한 책임: 작업 제출 + job_id 반환
이벤트 발행은 Worker에서 수행 (상태 변경의 source of truth)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from chat.application.chat.ports import JobSubmitterPort

logger = logging.getLogger(__name__)


@dataclass
class SubmitChatRequest:
    """채팅 제출 요청 DTO."""

    session_id: str
    user_id: str
    message: str
    image_url: str | None = None
    user_location: dict[str, float] | None = None
    model: str | None = None


@dataclass
class SubmitChatResponse:
    """채팅 제출 응답 DTO."""

    job_id: str
    session_id: str
    stream_url: str
    status: str


class SubmitChatCommand:
    """채팅 작업 제출 Command.

    책임:
    - job_id 생성
    - JobSubmitter를 통해 Worker에 작업 전달
    - stream_url 반환

    책임 아님 (Worker에서 수행):
    - 이벤트 발행 (queued, progress, done)
    - 상태 관리

    면접 포인트:
    Q: "API가 queued 이벤트를 발행하지 않으면 클라이언트는 어떻게 상태를 알죠?"
    A: "클라이언트는 stream_url로 SSE 연결 후 Worker가 발행하는 이벤트를 수신합니다.
        Worker가 작업을 수신하면 즉시 queued 이벤트를 발행합니다.
        이렇게 하면 '실제로 Worker가 작업을 받았을 때'만 queued가 되어
        상태의 일관성이 보장됩니다."
    """

    def __init__(self, job_submitter: JobSubmitterPort):
        self._job_submitter = job_submitter

    async def execute(
        self,
        request: SubmitChatRequest,
    ) -> SubmitChatResponse:
        """채팅 작업 제출 실행."""
        # 1. Job ID 생성
        job_id = str(uuid4())

        # 2. Worker에 작업 제출 (이벤트 발행은 Worker에서)
        success = await self._job_submitter.submit(
            job_id=job_id,
            session_id=request.session_id,
            user_id=request.user_id,
            message=request.message,
            image_url=request.image_url,
            user_location=request.user_location,
            model=request.model,
        )

        if not success:
            logger.error("Job submission failed", extra={"job_id": job_id})
            # 실패 시에도 job_id는 반환 (클라이언트가 재시도 가능)

        logger.info(
            "chat_submitted",
            extra={
                "job_id": job_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "model": request.model,
                "success": success,
            },
        )

        # 3. 응답 생성
        return SubmitChatResponse(
            job_id=job_id,
            session_id=request.session_id,
            stream_url=f"/api/v1/chat/{job_id}/events",
            status="submitted",  # "queued"가 아닌 "submitted" (Worker가 queued 발행)
        )
