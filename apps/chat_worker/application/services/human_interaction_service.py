"""Human Interaction Service - Human-in-the-Loop 비즈니스 로직.

"대기"를 품지 않고 "이벤트 발행 + 상태 저장"까지만 담당.
실제 대기/재개는 Infrastructure/Presentation에서 처리.

흐름:
1. request_location() → needs_input 이벤트 발행 + 상태 저장
2. (파이프라인 일시 중단, 상태: waiting_human)
3. Frontend가 입력 수집 → POST /chat/{job_id}/input
4. (Presentation에서 파이프라인 재개)

SoT 분리:
- InputRequesterPort: 이벤트 발행만
- InteractionStateStorePort: 상태 저장/조회

이 설계의 장점:
- Application은 순수 비즈니스 로직만 (blocking wait 없음)
- 테스트 용이
- 타임아웃 처리가 Infrastructure 책임
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.domain import HumanInputRequest, InputType

if TYPE_CHECKING:
    from chat_worker.application.ports.input_requester import InputRequesterPort
    from chat_worker.application.ports.interaction_state_store import (
        InteractionStateStorePort,
    )

logger = logging.getLogger(__name__)

# 기본 타임아웃 (초)
DEFAULT_TIMEOUT = 60

# 입력 타입별 기본 메시지
DEFAULT_MESSAGES = {
    InputType.LOCATION: "주변 센터를 찾으려면 위치 정보가 필요해요.\n" "위치 권한을 허용해주세요!",
    InputType.CONFIRMATION: "계속 진행할까요?",
}


class HumanInteractionService:
    """Human-in-the-Loop 비즈니스 로직 서비스.

    "이벤트 발행 + 상태 저장"까지만 담당.
    "대기/재개"는 Infrastructure/Presentation에서 처리.

    SoT 분리:
    - InputRequesterPort: needs_input 이벤트 발행
    - InteractionStateStorePort: 상태 저장/조회
    """

    def __init__(
        self,
        input_requester: "InputRequesterPort",
        state_store: "InteractionStateStorePort",
    ):
        self._requester = input_requester
        self._state_store = state_store

    async def request_location(
        self,
        job_id: str,
        current_state: dict[str, Any],
        message: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> str:
        """위치 정보 요청.

        1. needs_input 이벤트 발행
        2. 현재 상태 저장 (재개용)
        3. 입력 요청 저장 (SoT)

        Args:
            job_id: 작업 ID
            current_state: 현재 파이프라인 상태
            message: 사용자에게 표시할 메시지
            timeout: 응답 대기 시간 (초)

        Returns:
            요청 ID
        """
        logger.info(
            "Requesting location input",
            extra={"job_id": job_id, "timeout": timeout},
        )

        final_message = message or DEFAULT_MESSAGES[InputType.LOCATION]

        # 1. 이벤트 발행 (InputRequesterPort)
        request_id = await self._requester.request_input(
            job_id=job_id,
            input_type=InputType.LOCATION,
            message=final_message,
            timeout=timeout,
        )

        # 2. 파이프라인 상태 저장 (InteractionStateStorePort)
        await self._state_store.save_pipeline_state(
            job_id=job_id,
            state=current_state,
            resume_node="location_subagent",
        )

        # 3. 입력 요청 저장 (SoT)
        request = HumanInputRequest(
            job_id=job_id,
            input_type=InputType.LOCATION,
            message=final_message,
            timeout=timeout,
        )
        await self._state_store.save_pending_request(job_id, request)

        return request_id

    async def request_confirmation(
        self,
        job_id: str,
        current_state: dict[str, Any],
        message: str,
        resume_node: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> str:
        """확인 요청.

        Args:
            job_id: 작업 ID
            current_state: 현재 파이프라인 상태
            message: 확인 메시지
            resume_node: 재개할 노드 이름
            timeout: 응답 대기 시간 (초)

        Returns:
            요청 ID
        """
        logger.info(
            "Requesting confirmation",
            extra={"job_id": job_id, "resume_node": resume_node},
        )

        request_id = await self._requester.request_input(
            job_id=job_id,
            input_type=InputType.CONFIRMATION,
            message=message,
            timeout=timeout,
        )

        await self._state_store.save_pipeline_state(
            job_id=job_id,
            state=current_state,
            resume_node=resume_node,
        )

        request = HumanInputRequest(
            job_id=job_id,
            input_type=InputType.CONFIRMATION,
            message=message,
            timeout=timeout,
        )
        await self._state_store.save_pending_request(job_id, request)

        return request_id

    async def complete_interaction(self, job_id: str) -> None:
        """상호작용 완료 처리.

        입력을 받은 후 호출하여 상태 정리.

        Args:
            job_id: 작업 ID
        """
        logger.info("Completing interaction", extra={"job_id": job_id})
        await self._state_store.mark_completed(job_id)

    async def get_pending_state(
        self,
        job_id: str,
    ) -> tuple[dict[str, Any], str] | None:
        """대기 중인 파이프라인 상태 조회.

        재개 시 사용.

        Args:
            job_id: 작업 ID

        Returns:
            (상태, 재개 노드) 또는 None
        """
        return await self._state_store.get_pipeline_state(job_id)
