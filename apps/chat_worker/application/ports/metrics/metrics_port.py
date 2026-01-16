"""Metrics Port - 메트릭 인터페이스 정의.

Clean Architecture 원칙:
- Application Layer는 Infrastructure(Prometheus)를 직접 의존하지 않음
- 이 Port를 통해 메트릭 수집 기능을 추상화
- 테스트 시 NoOp 구현체로 교체 가능
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MetricsPort(ABC):
    """메트릭 Port.

    애플리케이션 메트릭 수집을 추상화합니다.
    Prometheus, StatsD, DataDog 등 다양한 백엔드로 교체 가능.

    사용 예시:
    - 요청 수/시간 추적
    - Intent 분포 추적
    - 에러 추적
    """

    @abstractmethod
    def track_request(
        self,
        intent: str,
        status: str,
        provider: str,
        duration: float,
    ) -> None:
        """요청 메트릭 기록.

        Args:
            intent: 분류된 Intent
            status: 처리 상태 (success/error)
            provider: LLM 프로바이더 (openai/gemini)
            duration: 처리 시간 (초)
        """
        raise NotImplementedError

    @abstractmethod
    def track_intent(self, intent: str) -> None:
        """Intent 분류 메트릭 기록.

        Args:
            intent: 분류된 Intent
        """
        raise NotImplementedError

    @abstractmethod
    def track_error(self, intent: str, error_type: str) -> None:
        """에러 메트릭 기록.

        Args:
            intent: 처리 중이던 Intent
            error_type: 에러 타입명
        """
        raise NotImplementedError

    # === 선택적 메서드 (기본 NoOp 구현) ===

    def track_cache_hit(self, cache_type: str) -> None:
        """캐시 히트 메트릭 기록.

        Args:
            cache_type: 캐시 종류 (intent/rag/profile)
        """
        pass

    def track_cache_miss(self, cache_type: str) -> None:
        """캐시 미스 메트릭 기록.

        Args:
            cache_type: 캐시 종류 (intent/rag/profile)
        """
        pass

    def track_subagent_call(
        self,
        subagent: str,
        status: str,
        duration: float,
    ) -> None:
        """서브에이전트 호출 메트릭 기록.

        Args:
            subagent: 서브에이전트명 (character/location/web_search)
            status: 호출 상태 (success/error)
            duration: 호출 시간 (초)
        """
        pass
