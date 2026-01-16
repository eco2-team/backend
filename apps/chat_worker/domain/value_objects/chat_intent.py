"""ChatIntent Value Object.

분류된 사용자 의도를 표현하는 불변 객체입니다.
"""

from dataclasses import dataclass

from chat_worker.domain.enums import Intent, QueryComplexity


@dataclass(frozen=True, slots=True)
class ChatIntent:
    """분류된 사용자 의도 (Immutable).

    IntentClassifier 서비스의 출력으로 사용되며,
    LangGraph의 라우팅 결정에 활용됩니다.

    Attributes:
        intent: 분류된 의도
        complexity: 질문 복잡도
        confidence: 분류 신뢰도 (0.0 ~ 1.0)
    """

    intent: Intent
    complexity: QueryComplexity
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Validation."""
        if not 0.0 <= self.confidence <= 1.0:
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))

    @property
    def is_complex(self) -> bool:
        """복잡한 질문인지 여부.

        Returns:
            True if complexity is COMPLEX
        """
        return self.complexity == QueryComplexity.COMPLEX

    @property
    def needs_subagent(self) -> bool:
        """Subagent 호출이 필요한지 여부.

        Returns:
            True if complexity is COMPLEX
        """
        return self.is_complex

    @property
    def is_high_confidence(self) -> bool:
        """높은 신뢰도인지 여부.

        Returns:
            True if confidence >= 0.8
        """
        return self.confidence >= 0.8

    @classmethod
    def simple_waste(cls, confidence: float = 1.0) -> "ChatIntent":
        """단순 분리배출 질문 생성."""
        return cls(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=confidence,
        )

    @classmethod
    def simple_general(cls, confidence: float = 1.0) -> "ChatIntent":
        """단순 일반 질문 생성."""
        return cls(
            intent=Intent.GENERAL,
            complexity=QueryComplexity.SIMPLE,
            confidence=confidence,
        )

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "confidence": self.confidence,
            "needs_subagent": self.needs_subagent,
        }
