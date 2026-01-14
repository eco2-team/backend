"""Input Requester Port - 사용자 입력 요청 추상화.

"대기"를 품지 않고 "요청 발행"만 담당.
상태 저장/조회는 InteractionStateStorePort에서 처리 (SoT 분리).

vs 기존 InputWaiterPort:
- InputWaiterPort: blocking wait 포함 (문제)
- InputRequesterPort: 이벤트 발행만 (권장)

상태 기반 재개 패턴:
1. Application: needs_input 이벤트 발행 (InputRequesterPort)
2. Application: 상태 저장 (InteractionStateStorePort)
3. Frontend: 입력 수집 → POST /chat/{job_id}/input
4. Infrastructure: 상태 복원 → 파이프라인 재개
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.domain import InputType


class InputRequesterPort(ABC):
    """사용자 입력 요청 포트.

    needs_input 이벤트 발행만 담당.
    상태 저장/조회는 InteractionStateStorePort 사용.
    """

    @abstractmethod
    async def request_input(
        self,
        job_id: str,
        input_type: "InputType",
        message: str,
        timeout: int = 60,
    ) -> str:
        """사용자 입력 요청 발행.

        needs_input 이벤트를 발행합니다.
        상태 저장은 InteractionStateStorePort에서 별도로 처리.

        Args:
            job_id: 작업 ID
            input_type: 입력 타입 (location, confirmation 등)
            message: 사용자에게 표시할 메시지
            timeout: 입력 대기 시간 (초)

        Returns:
            요청 ID (재개 시 사용)
        """
        pass
