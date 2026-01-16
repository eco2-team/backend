"""Query Complexity Enum.

질문의 복잡도를 분류하여 Subagent 분기를 결정합니다.
"""

from enum import Enum


class QueryComplexity(str, Enum):
    """질문 복잡도.

    LangGraph의 라우팅 결정에 사용됩니다.
    - SIMPLE: 직접 응답
    - COMPLEX: Subagent 호출
    """

    SIMPLE = "simple"
    """단순 질문 - 직접 응답 가능.

    - 단일 의도
    - 단일 Tool 호출 또는 LLM만으로 해결
    - 예: "플라스틱 어떻게 버려?"
    """

    COMPLEX = "complex"
    """복잡한 질문 - Subagent 필요.

    - 다중 의도 또는 다중 단계
    - 여러 Tool 조합 필요
    - 예: "이 쓰레기 버리면 어떤 캐릭터 얻고, 근처 재활용센터도 알려줘"
    """

    @classmethod
    def from_bool(cls, is_complex: bool) -> "QueryComplexity":
        """bool에서 QueryComplexity 생성."""
        return cls.COMPLEX if is_complex else cls.SIMPLE

    @classmethod
    def from_string(cls, value: str) -> "QueryComplexity":
        """문자열에서 QueryComplexity 생성.

        Args:
            value: 복잡도 문자열 (case-insensitive)

        Returns:
            매칭된 QueryComplexity, 없으면 SIMPLE
        """
        try:
            return cls(value.lower())
        except ValueError:
            return cls.SIMPLE
