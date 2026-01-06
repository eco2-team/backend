"""Get Result Query - 결과 조회."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from scan.application.result.ports import ResultCache

logger = logging.getLogger(__name__)


@dataclass
class ResultResponse:
    """결과 응답 DTO."""

    task_id: str
    status: str
    message: str | None
    pipeline_result: dict[str, Any] | None
    reward: dict[str, Any] | None
    error: str | None


@dataclass
class ProcessingResponse:
    """처리 중 응답 DTO (202 Accepted)."""

    status: str = "processing"
    message: str = "결과 준비 중입니다."
    current_stage: str | None = None
    progress: int | None = None


class GetResultQuery:
    """결과 조회 Query.

    Cache Redis에서 파이프라인 결과를 조회합니다.
    """

    def __init__(self, result_cache: ResultCache):
        """초기화.

        Args:
            result_cache: 결과 캐시 저장소
        """
        self._result_cache = result_cache

    async def execute(
        self,
        job_id: str,
    ) -> ResultResponse | ProcessingResponse | None:
        """결과 조회 실행.

        Args:
            job_id: 작업 ID (UUID)

        Returns:
            - ResultResponse: 완료된 결과
            - ProcessingResponse: 아직 처리 중
            - None: 작업을 찾을 수 없음
        """
        # 1. Cache에서 결과 조회
        result = await self._result_cache.get(job_id)

        if result is not None:
            logger.info("scan_result_found", extra={"job_id": job_id})
            return ResultResponse(
                task_id=result.get("task_id", job_id),
                status=result.get("status", "completed"),
                message=result.get("message"),
                pipeline_result=result.get("pipeline_result"),
                reward=result.get("reward"),
                error=result.get("error"),
            )

        # 2. State KV에서 현재 상태 확인
        state = await self._result_cache.get_state(job_id)

        if state is not None:
            # 작업이 존재하지만 결과가 아직 없음
            logger.info(
                "scan_result_processing",
                extra={"job_id": job_id, "stage": state.get("stage")},
            )
            progress = state.get("progress")
            return ProcessingResponse(
                status="processing",
                message="결과 준비 중입니다.",
                current_stage=state.get("stage"),
                progress=int(progress) if progress else None,
            )

        # 3. 작업 자체가 없음
        logger.warning("scan_result_not_found", extra={"job_id": job_id})
        return None
