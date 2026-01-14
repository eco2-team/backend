"""Interaction State Store Port - HITL 상태 저장/조회.

Source of Truth(SoT) 분리:
- InputRequesterPort: 이벤트 발행만 담당
- InteractionStateStorePort: 상태 저장/조회만 담당

상태 기반 재개 패턴:
1. Worker: needs_input 이벤트 발행 (InputRequesterPort)
2. Worker: 대기 상태 저장 (InteractionStateStorePort)
3. Frontend: 입력 수집 → POST /chat/{job_id}/input
4. API: 상태 조회 → 파이프라인 재개

vs 기존 InputWaiterPort:
- 기존: blocking wait 포함 (테스트/타임아웃 설계 어려움)
- 개선: 요청 발행 + 상태 저장/조회 분리 (테스트 용이, 상태 기반)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat_worker.domain import HumanInputRequest


class InteractionStateStorePort(ABC):
    """HITL 상태 저장/조회 포트.

    파이프라인 재개를 위한 상태 스냅샷 관리.
    """

    @abstractmethod
    async def save_pending_request(
        self,
        job_id: str,
        request: "HumanInputRequest",
    ) -> None:
        """대기 중인 입력 요청 저장.

        Args:
            job_id: 작업 ID
            request: 입력 요청 정보 (Domain VO)
        """
        pass

    @abstractmethod
    async def get_pending_request(
        self,
        job_id: str,
    ) -> "HumanInputRequest | None":
        """대기 중인 입력 요청 조회.

        Args:
            job_id: 작업 ID

        Returns:
            입력 요청 또는 None
        """
        pass

    @abstractmethod
    async def mark_completed(
        self,
        job_id: str,
    ) -> None:
        """입력 완료 처리.

        대기 중인 요청을 삭제하고 완료 상태로 전환.

        Args:
            job_id: 작업 ID
        """
        pass

    @abstractmethod
    async def save_pipeline_state(
        self,
        job_id: str,
        state: dict[str, Any],
        resume_node: str,
    ) -> None:
        """파이프라인 상태 스냅샷 저장.

        재개 시 필요한 LangGraph 상태.

        Args:
            job_id: 작업 ID
            state: 현재 파이프라인 상태
            resume_node: 재개할 노드 이름
        """
        pass

    @abstractmethod
    async def get_pipeline_state(
        self,
        job_id: str,
    ) -> tuple[dict[str, Any], str] | None:
        """파이프라인 상태 스냅샷 조회.

        Args:
            job_id: 작업 ID

        Returns:
            (상태, 재개 노드) 또는 None
        """
        pass

    @abstractmethod
    async def clear_state(
        self,
        job_id: str,
    ) -> None:
        """모든 상태 삭제.

        파이프라인 완료 후 정리.

        Args:
            job_id: 작업 ID
        """
        pass
