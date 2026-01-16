"""FailMode Enum.

노드 실패 시 처리 모드를 정의합니다.

Circuit Breaker 패턴과 함께 사용되어
각 노드의 실패 정책을 결정합니다.
"""

from enum import Enum


class FailMode(str, Enum):
    """노드 실패 처리 모드.

    NodePolicy와 함께 사용되어
    노드 실패 시 동작을 결정합니다.
    """

    FAIL_OPEN = "fail_open"
    """실패해도 진행 (선택적 노드).

    비필수 컨텍스트 노드에 적용:
    - character: 캐릭터 정보 없어도 답변 가능
    - weather: 날씨 정보 없어도 답변 가능
    - image_generation: 이미지 생성 실패해도 텍스트 답변 가능
    """

    FAIL_CLOSE = "fail_close"
    """실패하면 전체 실패 (필수 노드).

    핵심 노드에 적용:
    - general: LLM 호출 실패는 치명적
    - 최종 답변 생성이 실패하면 사용자에게 에러 표시
    """

    FAIL_FALLBACK = "fail_fallback"
    """실패하면 대체 로직 실행.

    대체 가능한 노드에 적용:
    - waste_rag: RAG 실패 시 LLM 직접 응답
    - location: 위치 검색 실패 시 기본 안내
    - bulk_waste: API 실패 시 일반 가이드 제공
    """

    @classmethod
    def from_string(cls, value: str) -> "FailMode":
        """문자열에서 FailMode 생성.

        Args:
            value: 실패 모드 문자열 (case-insensitive)

        Returns:
            매칭된 FailMode, 없으면 FAIL_CLOSE (안전 기본값)
        """
        try:
            return cls(value.lower())
        except ValueError:
            return cls.FAIL_CLOSE


__all__ = ["FailMode"]
