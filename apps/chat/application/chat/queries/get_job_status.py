"""Get Job Status Query (CQRS - Query).

작업 상태 조회.
읽기 전용 - 상태를 변경하지 않음.

아키텍처:
- Event Router가 Redis Streams → State KV로 집계
- 이 Query는 State KV (chat:state:{job_id})를 조회
- Streams 직접 조회 ❌ → State KV 조회 ✅

참조: docs/blogs/applied/14-chat-event-relay-sse.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# State KV 프리픽스 (event_router와 일치)
STATE_KEY_PREFIX = "chat:state"


@dataclass
class JobStatusResponse:
    """작업 상태 응답."""

    job_id: str
    status: str  # "submitted" | "queued" | "running" | "completed" | "failed"
    progress: int
    current_stage: str | None
    result: dict[str, Any] | None
    error: str | None = None


class GetJobStatusQuery:
    """작업 상태 조회 Query (CQRS).

    읽기 전용 작업:
    - State KV (chat:state:{job_id})에서 최신 상태 조회
    - Event Router가 Redis Streams를 집계하여 State KV에 저장
    - 상태 변경 없음

    CQRS 관점:
    - Query는 상태를 조회만 함
    - Command와 분리하여 독립적으로 스케일링 가능
    """

    def __init__(self, redis_client):
        self._redis = redis_client

    async def execute(self, job_id: str) -> JobStatusResponse:
        """작업 상태 조회.

        State KV에서 최신 상태 조회.
        Event Router가 Redis Streams → State KV로 집계.
        """
        state_key = f"{STATE_KEY_PREFIX}:{job_id}"

        try:
            # State KV에서 최신 상태 조회
            state_data = await self._redis.get(state_key)

            if not state_data:
                return JobStatusResponse(
                    job_id=job_id,
                    status="unknown",
                    progress=0,
                    current_stage=None,
                    result=None,
                )

            # JSON 파싱
            if isinstance(state_data, bytes):
                state_data = state_data.decode("utf-8")

            event = json.loads(state_data)

            stage = event.get("stage", "unknown")
            status = event.get("status", "unknown")

            # progress 파싱
            progress_raw = event.get("progress", 0)
            try:
                progress = int(progress_raw) if progress_raw else 0
            except (ValueError, TypeError):
                progress = 0

            # 상태 매핑
            if stage == "done":
                final_status = "completed" if status == "completed" else "failed"
            elif stage == "queued":
                final_status = "queued"
            else:
                final_status = "running"

            return JobStatusResponse(
                job_id=job_id,
                status=final_status,
                progress=progress,
                current_stage=stage,
                result=event.get("result"),
                error=event.get("error"),
            )

        except json.JSONDecodeError as e:
            logger.error("Failed to parse job state JSON: %s", e)
            return JobStatusResponse(
                job_id=job_id,
                status="error",
                progress=0,
                current_stage=None,
                result=None,
                error=f"Invalid state data: {e}",
            )
        except Exception as e:
            logger.error("Failed to get job status: %s", e)
            return JobStatusResponse(
                job_id=job_id,
                status="error",
                progress=0,
                current_stage=None,
                result=None,
                error=str(e),
            )
