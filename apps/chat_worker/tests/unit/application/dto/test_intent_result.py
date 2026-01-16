"""IntentResult DTO Unit Tests."""

import pytest

from chat_worker.application.dto.intent_result import IntentResult
from chat_worker.application.dto.intent_signals import IntentSignals
from chat_worker.domain import ChatIntent, Intent, QueryComplexity


class TestIntentResult:
    """IntentResult DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.85,
        )

        assert result.intent == Intent.WASTE
        assert result.complexity == QueryComplexity.SIMPLE
        assert result.confidence == 0.85
        assert result.raw_response is None
        assert result.rationale is None
        assert result.signals is None

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        signals = IntentSignals.from_llm_only(0.85)
        result = IntentResult(
            intent=Intent.CHARACTER,
            complexity=QueryComplexity.COMPLEX,
            confidence=0.90,
            raw_response='{"intent": "character"}',
            rationale="캐릭터 키워드 감지",
            signals=signals,
        )

        assert result.intent == Intent.CHARACTER
        assert result.complexity == QueryComplexity.COMPLEX
        assert result.confidence == 0.90
        assert result.raw_response == '{"intent": "character"}'
        assert result.rationale == "캐릭터 키워드 감지"
        assert result.signals is not None

    def test_from_chat_intent(self) -> None:
        """ChatIntent에서 생성."""
        chat_intent = ChatIntent(
            intent=Intent.LOCATION,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.75,
        )

        result = IntentResult.from_chat_intent(
            chat_intent=chat_intent,
            raw_response="raw llm output",
            rationale="위치 키워드 감지",
        )

        assert result.intent == Intent.LOCATION
        assert result.complexity == QueryComplexity.SIMPLE
        assert result.confidence == 0.75
        assert result.raw_response == "raw llm output"
        assert result.rationale == "위치 키워드 감지"

    def test_is_waste_related(self) -> None:
        """폐기물 관련 의도 확인."""
        waste_result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        general_result = IntentResult(
            intent=Intent.GENERAL,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )

        assert waste_result.is_waste_related() is True
        assert general_result.is_waste_related() is False

    def test_is_location_related(self) -> None:
        """위치 관련 의도 확인."""
        location_result = IntentResult(
            intent=Intent.LOCATION,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        waste_result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )

        assert location_result.is_location_related() is True
        assert waste_result.is_location_related() is False

    def test_is_character_related(self) -> None:
        """캐릭터 관련 의도 확인."""
        char_result = IntentResult(
            intent=Intent.CHARACTER,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        waste_result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )

        assert char_result.is_character_related() is True
        assert waste_result.is_character_related() is False

    def test_is_complex(self) -> None:
        """복잡한 쿼리 확인."""
        simple_result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.9,
        )
        complex_result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.COMPLEX,
            confidence=0.9,
        )

        assert simple_result.is_complex() is False
        assert complex_result.is_complex() is True

    def test_to_dict_basic(self) -> None:
        """딕셔너리 변환 (기본)."""
        result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.85,
        )

        d = result.to_dict()

        assert d["intent"] == "waste"
        assert d["complexity"] == "simple"
        assert d["confidence"] == 0.85
        assert d["raw_response"] is None
        assert d["rationale"] is None
        assert d["signals"] is None

    def test_to_dict_with_signals(self) -> None:
        """딕셔너리 변환 (signals 포함)."""
        signals = IntentSignals(
            llm_confidence=0.8,
            keyword_boost=0.05,
        )
        result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.85,
            signals=signals,
        )

        d = result.to_dict()

        assert d["signals"] is not None
        assert d["signals"]["llm_confidence"] == 0.8
        assert d["signals"]["keyword_boost"] == 0.05

    def test_immutable(self) -> None:
        """불변성 테스트."""
        result = IntentResult(
            intent=Intent.WASTE,
            complexity=QueryComplexity.SIMPLE,
            confidence=0.85,
        )

        with pytest.raises(AttributeError):
            result.intent = Intent.GENERAL  # type: ignore

    def test_all_intent_types(self) -> None:
        """모든 의도 타입으로 생성 가능."""
        intents = [
            Intent.WASTE,
            Intent.CHARACTER,
            Intent.LOCATION,
            Intent.BULK_WASTE,
            Intent.RECYCLABLE_PRICE,
            Intent.COLLECTION_POINT,
            Intent.WEB_SEARCH,
            Intent.IMAGE_GENERATION,
            Intent.GENERAL,
        ]

        for intent in intents:
            result = IntentResult(
                intent=intent,
                complexity=QueryComplexity.SIMPLE,
                confidence=0.8,
            )
            assert result.intent == intent
