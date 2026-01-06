"""Step Interface - 파이프라인 단계 추상화."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )

T = TypeVar("T", bound="ClassifyContext")


class Step(ABC):
    """파이프라인 Step 인터페이스.

    모든 Step은 이 인터페이스를 구현.
    Context만 공유하여 모듈 의존 그래프가 아닌 데이터 흐름 그래프.

    Stateless Reducer 패턴:
    - 각 Step은 순수 함수처럼 동작
    - 입력 Context → 처리 → 업데이트된 Context 반환
    - 외부 상태 변경 없음 (이벤트 발행 제외)
    """

    @abstractmethod
    def run(self, ctx: T) -> T:
        """Step 실행.

        Args:
            ctx: 입력 Context

        Returns:
            업데이트된 Context
        """
        pass
