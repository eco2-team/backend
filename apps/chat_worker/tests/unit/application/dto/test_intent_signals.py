"""IntentSignals DTO Unit Tests."""

import pytest

from chat_worker.application.dto.intent_signals import IntentSignals


class TestIntentSignals:
    """IntentSignals DTO 테스트."""

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        signals = IntentSignals(
            llm_confidence=0.75,
            keyword_boost=0.10,
            transition_boost=0.05,
            length_penalty=-0.05,
        )

        assert signals.llm_confidence == 0.75
        assert signals.keyword_boost == 0.10
        assert signals.transition_boost == 0.05
        assert signals.length_penalty == -0.05

    def test_create_with_defaults(self) -> None:
        """기본값으로 생성."""
        signals = IntentSignals(llm_confidence=0.8)

        assert signals.llm_confidence == 0.8
        assert signals.keyword_boost == 0.0
        assert signals.transition_boost == 0.0
        assert signals.length_penalty == 0.0

    def test_final_confidence_calculation(self) -> None:
        """최종 신뢰도 계산."""
        signals = IntentSignals(
            llm_confidence=0.75,
            keyword_boost=0.10,
            transition_boost=0.05,
            length_penalty=-0.05,
        )

        # 0.75 + 0.10 + 0.05 - 0.05 = 0.85
        assert signals.final_confidence == 0.85

    def test_final_confidence_clamping_upper(self) -> None:
        """최종 신뢰도 상한 클램핑 (1.0 초과 시)."""
        signals = IntentSignals(
            llm_confidence=0.90,
            keyword_boost=0.20,
            transition_boost=0.15,
            length_penalty=0.0,
        )

        # 0.90 + 0.20 + 0.15 = 1.25 → clamped to 1.0
        assert signals.final_confidence == 1.0

    def test_final_confidence_clamping_lower(self) -> None:
        """최종 신뢰도 하한 클램핑 (0.0 미만 시)."""
        signals = IntentSignals(
            llm_confidence=0.10,
            keyword_boost=0.0,
            transition_boost=0.0,
            length_penalty=-0.20,
        )

        # 0.10 - 0.20 = -0.10 → clamped to 0.0
        assert signals.final_confidence == 0.0

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        signals = IntentSignals(
            llm_confidence=0.80,
            keyword_boost=0.05,
            transition_boost=0.0,
            length_penalty=-0.10,
        )

        result = signals.to_dict()

        assert result["llm_confidence"] == 0.80
        assert result["keyword_boost"] == 0.05
        assert result["transition_boost"] == 0.0
        assert result["length_penalty"] == -0.10
        # Use pytest.approx for floating point comparison
        assert result["final_confidence"] == pytest.approx(0.75)

    def test_from_llm_only(self) -> None:
        """LLM 신뢰도만으로 생성."""
        signals = IntentSignals.from_llm_only(0.9)

        assert signals.llm_confidence == 0.9
        assert signals.keyword_boost == 0.0
        assert signals.transition_boost == 0.0
        assert signals.length_penalty == 0.0
        assert signals.final_confidence == 0.9

    def test_immutable(self) -> None:
        """불변성 테스트."""
        signals = IntentSignals(llm_confidence=0.8)

        with pytest.raises(AttributeError):
            signals.llm_confidence = 0.9  # type: ignore

    def test_zero_confidence(self) -> None:
        """신뢰도 0인 경우."""
        signals = IntentSignals(llm_confidence=0.0)

        assert signals.final_confidence == 0.0

    def test_max_confidence(self) -> None:
        """신뢰도 1.0인 경우."""
        signals = IntentSignals(llm_confidence=1.0)

        assert signals.final_confidence == 1.0
