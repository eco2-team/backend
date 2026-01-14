"""Intent Result DTO - 의도 분류 결과.

Domain Layer의 ChatIntent를 Application Layer에서 사용하기 위한 DTO.

vs Domain VO (ChatIntent):
- Domain: 비즈니스 규칙과 불변성 보장
- DTO: 레이어 간 데이터 전송, 직렬화 가능

실제로 ChatIntent를 그대로 반환해도 무방하나,
명시적 분리를 위해 별도 클래스로 정의.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_worker.domain import ChatIntent, Intent, QueryComplexity


@dataclass(frozen=True)
class IntentResult:
    """의도 분류 결과 DTO.

    Attributes:
        intent: 분류된 의도 (Domain Enum)
        complexity: 쿼리 복잡도 (Domain Enum)
        confidence: 분류 신뢰도 (0.0 ~ 1.0)
        raw_response: LLM 원본 응답 (디버깅용)
    """

    intent: "Intent"
    complexity: "QueryComplexity"
    confidence: float
    raw_response: str | None = None

    @classmethod
    def from_chat_intent(
        cls,
        chat_intent: "ChatIntent",
        raw_response: str | None = None,
    ) -> "IntentResult":
        """Domain VO에서 DTO 생성."""
        return cls(
            intent=chat_intent.intent,
            complexity=chat_intent.complexity,
            confidence=chat_intent.confidence,
            raw_response=raw_response,
        )

    def is_waste_related(self) -> bool:
        """폐기물 관련 의도인지 확인."""
        from chat_worker.domain import Intent

        return self.intent == Intent.WASTE

    def is_location_related(self) -> bool:
        """위치 관련 의도인지 확인."""
        from chat_worker.domain import Intent

        return self.intent == Intent.LOCATION

    def is_character_related(self) -> bool:
        """캐릭터 관련 의도인지 확인."""
        from chat_worker.domain import Intent

        return self.intent == Intent.CHARACTER

    def is_complex(self) -> bool:
        """복잡한 쿼리인지 확인."""
        from chat_worker.domain import QueryComplexity

        return self.complexity == QueryComplexity.COMPLEX

    def to_dict(self) -> dict:
        """직렬화용 딕셔너리 변환."""
        return {
            "intent": self.intent.value,
            "complexity": self.complexity.value,
            "confidence": self.confidence,
            "raw_response": self.raw_response,
        }
