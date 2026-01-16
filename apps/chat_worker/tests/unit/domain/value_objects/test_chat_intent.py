"""ChatIntent Value Object Unit Tests."""

import pytest

from chat_worker.domain.enums import Intent, QueryComplexity
from chat_worker.domain.value_objects.chat_intent import ChatIntent


class TestChatIntent:
    """ChatIntent Value Object 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
        )

        assert chat_intent.intent == Intent.WASTE
        assert chat_intent.complexity == QueryComplexity.SIMPLE
        assert chat_intent.confidence == 1.0

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        chat_intent = ChatIntent(
            intent=Intent.CHARACTER,
            complexity=QueryComplexity.COMPLEX,
            confidence=0.85,
        )

        assert chat_intent.intent == Intent.CHARACTER
        assert chat_intent.complexity == QueryComplexity.COMPLEX
        assert chat_intent.confidence == 0.85

    def test_confidence_clamping_upper(self) -> None:
        """신뢰도 상한 클램핑."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=1.5,
        )

        assert chat_intent.confidence == 1.0

    def test_confidence_clamping_lower(self) -> None:
        """신뢰도 하한 클램핑."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=-0.5,
        )

        assert chat_intent.confidence == 0.0

    def test_is_complex_true(self) -> None:
        """is_complex 프로퍼티 (COMPLEX)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.COMPLEX,
        )

        assert chat_intent.is_complex is True

    def test_is_complex_false(self) -> None:
        """is_complex 프로퍼티 (SIMPLE)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
        )

        assert chat_intent.is_complex is False

    def test_needs_subagent_complex(self) -> None:
        """needs_subagent 프로퍼티 (COMPLEX)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.COMPLEX,
        )

        assert chat_intent.needs_subagent is True

    def test_needs_subagent_simple(self) -> None:
        """needs_subagent 프로퍼티 (SIMPLE)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
        )

        assert chat_intent.needs_subagent is False

    def test_is_high_confidence_true(self) -> None:
        """is_high_confidence 프로퍼티 (>= 0.8)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.85,
        )

        assert chat_intent.is_high_confidence is True

    def test_is_high_confidence_boundary(self) -> None:
        """is_high_confidence 경계값 (0.8)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.8,
        )

        assert chat_intent.is_high_confidence is True

    def test_is_high_confidence_false(self) -> None:
        """is_high_confidence 프로퍼티 (< 0.8)."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.79,
        )

        assert chat_intent.is_high_confidence is False

    def test_simple_waste_factory(self) -> None:
        """simple_waste 팩토리 메서드."""
        chat_intent = ChatIntent.simple_waste(confidence=0.9)

        assert chat_intent.intent == Intent.WASTE
        assert chat_intent.complexity == QueryComplexity.SIMPLE
        assert chat_intent.confidence == 0.9

    def test_simple_waste_default_confidence(self) -> None:
        """simple_waste 기본 신뢰도."""
        chat_intent = ChatIntent.simple_waste()

        assert chat_intent.confidence == 1.0

    def test_simple_general_factory(self) -> None:
        """simple_general 팩토리 메서드."""
        chat_intent = ChatIntent.simple_general(confidence=0.7)

        assert chat_intent.intent == Intent.GENERAL
        assert chat_intent.complexity == QueryComplexity.SIMPLE
        assert chat_intent.confidence == 0.7

    def test_simple_general_default_confidence(self) -> None:
        """simple_general 기본 신뢰도."""
        chat_intent = ChatIntent.simple_general()

        assert chat_intent.confidence == 1.0

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        chat_intent = ChatIntent(
            intent=Intent.LOCATION,
            complexity=QueryComplexity.COMPLEX,
            confidence=0.75,
        )

        d = chat_intent.to_dict()

        assert d["intent"] == "location"
        assert d["complexity"] == "complex"
        assert d["confidence"] == 0.75
        assert d["needs_subagent"] is True

    def test_immutable(self) -> None:
        """불변성 테스트."""
        chat_intent = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
        )

        with pytest.raises(AttributeError):
            chat_intent.intent = Intent.GENERAL  # type: ignore

    def test_equality(self) -> None:
        """동등성 테스트."""
        intent1 = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        intent2 = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )

        assert intent1 == intent2

    def test_inequality(self) -> None:
        """비동등성 테스트."""
        intent1 = ChatIntent(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        intent2 = ChatIntent(
            intent=Intent.GENERAL,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )

        assert intent1 != intent2

    def test_all_intent_types(self) -> None:
        """모든 의도 타입으로 생성 가능."""
        for intent in Intent:
            chat_intent = ChatIntent(
                intent=intent,
                complexity=QueryComplexity.SIMPLE,
            )
            assert chat_intent.intent == intent
