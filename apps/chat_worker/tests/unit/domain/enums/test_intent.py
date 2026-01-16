"""Intent Enum Unit Tests."""

import pytest

from chat_worker.domain.enums.intent import Intent


class TestIntent:
    """Intent Enum 테스트."""

    def test_all_intent_values(self) -> None:
        """모든 의도 값 확인."""
        assert Intent.WASTE.value == "waste"
        assert Intent.CHARACTER.value == "character"
        assert Intent.LOCATION.value == "location"
        assert Intent.BULK_WASTE.value == "bulk_waste"
        assert Intent.RECYCLABLE_PRICE.value == "recyclable_price"
        assert Intent.COLLECTION_POINT.value == "collection_point"
        assert Intent.WEB_SEARCH.value == "web_search"
        assert Intent.IMAGE_GENERATION.value == "image_generation"
        assert Intent.GENERAL.value == "general"

    def test_from_string_valid(self) -> None:
        """유효한 문자열에서 생성."""
        assert Intent.from_string("waste") == Intent.WASTE
        assert Intent.from_string("character") == Intent.CHARACTER
        assert Intent.from_string("location") == Intent.LOCATION
        assert Intent.from_string("bulk_waste") == Intent.BULK_WASTE
        assert Intent.from_string("recyclable_price") == Intent.RECYCLABLE_PRICE
        assert Intent.from_string("collection_point") == Intent.COLLECTION_POINT
        assert Intent.from_string("web_search") == Intent.WEB_SEARCH
        assert Intent.from_string("image_generation") == Intent.IMAGE_GENERATION
        assert Intent.from_string("general") == Intent.GENERAL

    def test_from_string_case_insensitive(self) -> None:
        """대소문자 구분 없이 변환."""
        assert Intent.from_string("WASTE") == Intent.WASTE
        assert Intent.from_string("Waste") == Intent.WASTE
        assert Intent.from_string("WaStE") == Intent.WASTE

    def test_from_string_invalid_returns_general(self) -> None:
        """유효하지 않은 문자열은 GENERAL 반환."""
        assert Intent.from_string("invalid") == Intent.GENERAL
        assert Intent.from_string("unknown") == Intent.GENERAL
        assert Intent.from_string("") == Intent.GENERAL

    def test_intent_is_string_enum(self) -> None:
        """Intent는 str 기반 Enum."""
        assert isinstance(Intent.WASTE.value, str)
        assert Intent.WASTE.value == "waste"

    def test_intent_comparison(self) -> None:
        """의도 비교."""
        assert Intent.WASTE == Intent.WASTE
        assert Intent.WASTE != Intent.GENERAL
        assert Intent.WASTE == "waste"

    def test_intent_count(self) -> None:
        """총 의도 수 확인."""
        all_intents = list(Intent)
        assert len(all_intents) == 9

    def test_intent_in_set(self) -> None:
        """Set에서 사용 가능."""
        waste_intents = {Intent.WASTE, Intent.BULK_WASTE, Intent.RECYCLABLE_PRICE}

        assert Intent.WASTE in waste_intents
        assert Intent.GENERAL not in waste_intents

    def test_intent_iteration(self) -> None:
        """반복 가능."""
        intents = [i for i in Intent]
        assert Intent.WASTE in intents
        assert Intent.GENERAL in intents
