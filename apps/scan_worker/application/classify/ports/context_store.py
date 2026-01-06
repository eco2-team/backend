"""Context Store Port - 체크포인팅 추상화.

Stateless Reducer 패턴의 재현성(Reproducibility) 보장.
각 Step 완료 시 Context를 저장하여 실패 복구 지원.
"""

from abc import ABC, abstractmethod
from typing import Any


class ContextStorePort(ABC):
    """Context 저장소 포트 - 체크포인팅.

    실패 시 마지막 성공 지점부터 재시작 가능.
    LLM 재호출 비용 절감.
    """

    @abstractmethod
    def save_checkpoint(
        self,
        task_id: str,
        step_name: str,
        context: dict[str, Any],
    ) -> None:
        """Step 완료 후 Context 저장.

        Args:
            task_id: 작업 ID
            step_name: 완료된 Step 이름 (vision, rule, answer, reward)
            context: 저장할 Context (ctx.to_dict())
        """
        pass

    @abstractmethod
    def get_checkpoint(
        self,
        task_id: str,
        step_name: str,
    ) -> dict[str, Any] | None:
        """저장된 체크포인트 조회.

        Args:
            task_id: 작업 ID
            step_name: Step 이름

        Returns:
            저장된 Context (없으면 None)
        """
        pass

    @abstractmethod
    def get_latest_checkpoint(
        self,
        task_id: str,
    ) -> tuple[str, dict[str, Any]] | None:
        """가장 최근 체크포인트 조회.

        Args:
            task_id: 작업 ID

        Returns:
            (step_name, context) 튜플 (없으면 None)
        """
        pass

    @abstractmethod
    def clear_checkpoints(self, task_id: str) -> None:
        """작업의 모든 체크포인트 삭제.

        Args:
            task_id: 작업 ID
        """
        pass
