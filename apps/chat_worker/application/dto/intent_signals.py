"""Intent Signals DTO.

의도 분류 신뢰도를 구성하는 개별 신호들.

왜 분리된 신호가 필요한가?
- 디버깅: confidence 0.75가 왜 나왔는지 역추적
- 튜닝: 어떤 신호가 지배적인지 파악 후 조정
- 투명성: 면접/코드리뷰 시 판단 근거 설명
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentSignals:
    """의도 분류 신호 분해.

    최종 confidence = llm_confidence + keyword_boost + transition_boost + length_penalty
    (0.0 ~ 1.0 범위 클램핑)

    Attributes:
        llm_confidence: LLM이 반환한 기본 신뢰도 (0.0 ~ 1.0)
        keyword_boost: 키워드 매칭으로 인한 부스트 (0.0 ~ 0.2)
        transition_boost: Chain-of-Intent 전이 부스트 (0.0 ~ 0.15)
        length_penalty: 짧은 메시지 페널티 (-0.2 ~ 0.0)

    Example:
        >>> signals = IntentSignals(
        ...     llm_confidence=0.75,
        ...     keyword_boost=0.10,
        ...     transition_boost=0.05,
        ...     length_penalty=-0.05,
        ... )
        >>> signals.final_confidence
        0.85
    """

    llm_confidence: float
    keyword_boost: float = 0.0
    transition_boost: float = 0.0
    length_penalty: float = 0.0

    @property
    def final_confidence(self) -> float:
        """최종 신뢰도 계산 (0.0 ~ 1.0 클램핑).

        Returns:
            개별 신호 합산 후 클램핑된 신뢰도
        """
        raw = (
            self.llm_confidence
            + self.keyword_boost
            + self.transition_boost
            + self.length_penalty
        )
        return max(0.0, min(1.0, raw))

    def to_dict(self) -> dict:
        """직렬화용 딕셔너리 변환."""
        return {
            "llm_confidence": self.llm_confidence,
            "keyword_boost": self.keyword_boost,
            "transition_boost": self.transition_boost,
            "length_penalty": self.length_penalty,
            "final_confidence": self.final_confidence,
        }

    @classmethod
    def from_llm_only(cls, confidence: float) -> "IntentSignals":
        """LLM 신뢰도만으로 생성 (부스트 없음).

        Args:
            confidence: LLM 기본 신뢰도

        Returns:
            부스트 없는 IntentSignals
        """
        return cls(llm_confidence=confidence)


__all__ = ["IntentSignals"]
