"""IntentClassifierService 단위 테스트.

IntentClassifierService는 순수 로직만 담당 (Port 의존 없음):
- 프롬프트 구성
- LLM 응답 파싱
- 신뢰도 계산
- 복잡도 판단
- Multi-Intent 키워드 감지

Port 호출 테스트는 ClassifyIntentCommand 테스트에서 수행.
"""

from __future__ import annotations

import pytest

from chat_worker.application.services.intent_classifier_service import (
    COMPLEX_KEYWORDS,
    INTENT_CACHE_TTL,
    MULTI_INTENT_CANDIDATE_KEYWORDS,
    IntentClassificationResult,
    IntentClassifierService,
)
from chat_worker.domain import Intent, QueryComplexity


class TestIntentClassifierService:
    """IntentClassifierService 테스트 스위트 (순수 로직)."""

    @pytest.fixture
    def service(self) -> IntentClassifierService:
        """테스트용 서비스."""
        return IntentClassifierService(
            intent_prompt="테스트 프롬프트",
            decompose_prompt="분해 프롬프트",
            multi_detect_prompt="Multi-Intent 감지 프롬프트",
        )

    # ==========================================================
    # Prompt 구성 Tests
    # ==========================================================

    def test_get_intent_system_prompt(self, service: IntentClassifierService):
        """시스템 프롬프트 반환."""
        prompt = service.get_intent_system_prompt()
        assert prompt == "테스트 프롬프트"

    def test_get_decompose_system_prompt(self, service: IntentClassifierService):
        """분해 시스템 프롬프트 반환."""
        prompt = service.get_decompose_system_prompt()
        assert prompt == "분해 프롬프트"

    def test_get_multi_detect_system_prompt(self, service: IntentClassifierService):
        """Multi-Intent 감지 시스템 프롬프트 반환."""
        prompt = service.get_multi_detect_system_prompt()
        assert prompt == "Multi-Intent 감지 프롬프트"

    def test_build_prompt_with_context_no_context(self, service: IntentClassifierService):
        """맥락 없이 프롬프트 구성."""
        prompt = service.build_prompt_with_context("페트병 어떻게 버려?", None)
        assert prompt == "페트병 어떻게 버려?"

    def test_build_prompt_with_context_with_previous_intents(
        self, service: IntentClassifierService
    ):
        """이전 Intent 맥락 포함."""
        context = {"previous_intents": ["waste", "character"]}
        prompt = service.build_prompt_with_context("뭐야?", context)

        assert "[이전 의도:" in prompt
        assert "waste" in prompt
        assert "character" in prompt

    def test_build_prompt_with_context_empty_previous_intents(
        self, service: IntentClassifierService
    ):
        """빈 이전 Intent - context가 있으면 현재 메시지 레이블 추가."""
        context = {"previous_intents": []}
        prompt = service.build_prompt_with_context("테스트", context)
        # context가 존재하면 (빈 리스트라도) 현재 메시지 레이블이 붙음
        assert "[현재 메시지]" in prompt
        assert "테스트" in prompt

    # ==========================================================
    # LLM 응답 파싱 Tests
    # ==========================================================

    def test_parse_intent_response_waste(self, service: IntentClassifierService):
        """waste 응답 파싱."""
        result = service.parse_intent_response(
            llm_response="waste",
            message="페트병 어떻게 버려?",
        )

        assert result.intent == Intent.WASTE
        assert result.confidence >= 1.0  # 키워드 매칭 보정

    def test_parse_intent_response_character(self, service: IntentClassifierService):
        """character 응답 파싱."""
        result = service.parse_intent_response(
            llm_response="character",
            message="캐릭터 뭐야?",
        )

        assert result.intent == Intent.CHARACTER

    def test_parse_intent_response_location(self, service: IntentClassifierService):
        """location 응답 파싱."""
        result = service.parse_intent_response(
            llm_response="location",
            message="근처 센터 어디야?",
        )

        assert result.intent == Intent.LOCATION

    def test_parse_intent_response_strips_whitespace(self, service: IntentClassifierService):
        """공백 제거."""
        result = service.parse_intent_response(
            llm_response="  waste  \n",
            message="페트병",
        )

        assert result.intent == Intent.WASTE

    def test_parse_intent_response_case_insensitive(self, service: IntentClassifierService):
        """대소문자 무관."""
        result = service.parse_intent_response(
            llm_response="WASTE",
            message="페트병",
        )

        assert result.intent == Intent.WASTE

    def test_parse_intent_response_unknown_fallback(self, service: IntentClassifierService):
        """알 수 없는 응답은 general로."""
        result = service.parse_intent_response(
            llm_response="unknown_xyz",
            message="아무거나",
        )

        assert result.intent == Intent.GENERAL

    def test_parse_intent_response_low_confidence_fallback(self, service: IntentClassifierService):
        """낮은 신뢰도는 general로."""
        # 유효하지 않은 응답(-0.3) + 짧은 메시지(-0.2) + 키워드 없음(-0.1)
        result = service.parse_intent_response(
            llm_response="xyz",  # 유효하지 않은 응답
            message="응?",  # 짧은 메시지
        )

        assert result.intent == Intent.GENERAL
        assert result.confidence < 0.6

    # ==========================================================
    # 신뢰도 계산 Tests
    # ==========================================================

    def test_confidence_boosted_by_keywords(self, service: IntentClassifierService):
        """키워드 매칭으로 신뢰도 상승."""
        result = service.parse_intent_response(
            llm_response="waste",
            message="페트병 분리해서 버려야 해?",  # "분리", "버려" 두 키워드
        )

        assert result.confidence == 1.0  # max clamp

    def test_confidence_reduced_for_short_message(self, service: IntentClassifierService):
        """짧은 메시지는 신뢰도 감소."""
        result = service.parse_intent_response(
            llm_response="waste",
            message="뭐야",  # 5자 미만
        )

        assert result.confidence < 1.0

    def test_confidence_reduced_for_invalid_response(self, service: IntentClassifierService):
        """유효하지 않은 응답은 신뢰도 감소."""
        result = service.parse_intent_response(
            llm_response="invalid_response",
            message="페트병 어떻게 버려?",
        )

        # 유효하지 않은 응답(-0.3)
        assert result.confidence < 1.0

    # ==========================================================
    # 복잡도 판단 Tests
    # ==========================================================

    def test_is_complex_query_with_keyword(self, service: IntentClassifierService):
        """복잡도 키워드 감지."""
        assert service.is_complex_query("페트병 그리고 유리병") is True
        assert service.is_complex_query("비교해줘") is True
        assert service.is_complex_query("여러 가지") is True

    def test_is_complex_query_long_message(self, service: IntentClassifierService):
        """긴 메시지는 복잡한 쿼리."""
        long_message = "a" * 101
        assert service.is_complex_query(long_message) is True

    def test_is_complex_query_simple(self, service: IntentClassifierService):
        """단순 쿼리."""
        assert service.is_complex_query("페트병 버려") is False

    def test_all_complex_keywords(self, service: IntentClassifierService):
        """모든 복잡도 키워드 테스트."""
        for keyword in COMPLEX_KEYWORDS:
            message = f"테스트 {keyword} 메시지"
            assert service.is_complex_query(message) is True

    def test_parse_intent_response_complexity(self, service: IntentClassifierService):
        """파싱 결과에 복잡도 포함."""
        result = service.parse_intent_response(
            llm_response="waste",
            message="페트병 그리고 유리병 어떻게 버려?",
        )

        assert result.is_complex is True

    # ==========================================================
    # Multi-Intent 키워드 감지 Tests
    # ==========================================================

    def test_has_multi_intent_keywords(self, service: IntentClassifierService):
        """Multi-Intent 후보 키워드 감지."""
        for keyword in MULTI_INTENT_CANDIDATE_KEYWORDS:
            message = f"페트병 버리{keyword} 캐릭터 알려줘"
            assert service.has_multi_intent_keywords(message) is True

    def test_no_multi_intent_keywords(self, service: IntentClassifierService):
        """Multi-Intent 키워드 없음."""
        assert service.has_multi_intent_keywords("페트병 어떻게 버려") is False

    def test_is_definitely_single_intent_short(self, service: IntentClassifierService):
        """짧은 메시지는 확실히 단일 Intent."""
        assert service.is_definitely_single_intent("페트병 버려") is True
        assert service.is_definitely_single_intent("안녕") is True

    def test_is_definitely_single_intent_simple_question(self, service: IntentClassifierService):
        """단순 의문사는 확실히 단일 Intent."""
        assert service.is_definitely_single_intent("뭐야?") is True
        assert service.is_definitely_single_intent("어디") is True

    def test_has_multi_intent_combined(self, service: IntentClassifierService):
        """Multi-Intent 가능성 판별."""
        # 짧은 메시지 → False
        assert service.has_multi_intent("안녕") is False

        # 키워드 없음 → False
        assert service.has_multi_intent("페트병 어떻게 버려요 알려주세요") is False

        # 키워드 있음 → True
        assert service.has_multi_intent("페트병 버리고 캐릭터도 알려줘") is True

    # ==========================================================
    # Multi-Intent 응답 파싱 Tests
    # ==========================================================

    def test_parse_multi_detect_response_valid(self, service: IntentClassifierService):
        """Multi-Intent 감지 응답 파싱."""
        response = '{"is_multi": true, "reason": "waste와 character", "detected_categories": ["waste", "character"], "confidence": 0.9}'

        result = service.parse_multi_detect_response(response)

        assert result.is_multi is True
        assert result.reason == "waste와 character"
        assert result.detected_categories == ["waste", "character"]
        assert result.confidence == 0.9

    def test_parse_multi_detect_response_invalid_json(self, service: IntentClassifierService):
        """잘못된 JSON."""
        result = service.parse_multi_detect_response("invalid json")

        assert result.is_multi is False
        assert result.reason == "parsing_error"

    def test_parse_decompose_response_valid(self, service: IntentClassifierService):
        """Query Decomposition 응답 파싱."""
        response = '{"is_compound": true, "queries": ["페트병 버려", "캐릭터 알려줘"]}'

        result = service.parse_decompose_response(response, "원본")

        assert result.is_compound is True
        assert result.queries == ["페트병 버려", "캐릭터 알려줘"]
        assert result.original == "원본"

    def test_parse_decompose_response_invalid_json(self, service: IntentClassifierService):
        """잘못된 JSON."""
        result = service.parse_decompose_response("invalid", "원본")

        assert result.is_compound is False
        assert result.queries == ["원본"]

    # ==========================================================
    # 캐시 키 생성 Tests
    # ==========================================================

    def test_generate_cache_key(self, service: IntentClassifierService):
        """캐시 키 생성."""
        key1 = service.generate_cache_key("페트병 어떻게 버려?")
        key2 = service.generate_cache_key("페트병 어떻게 버려?")
        key3 = service.generate_cache_key("다른 메시지")

        assert key1 == key2  # 같은 메시지 = 같은 키
        assert key1 != key3  # 다른 메시지 = 다른 키
        assert key1.startswith("intent:")

    def test_generate_cache_key_case_insensitive(self, service: IntentClassifierService):
        """대소문자 무관."""
        key1 = service.generate_cache_key("TEST")
        key2 = service.generate_cache_key("test")

        assert key1 == key2

    def test_generate_multi_detect_cache_key(self, service: IntentClassifierService):
        """Multi-Intent 감지 캐시 키 생성."""
        key = service.generate_multi_detect_cache_key("테스트")

        assert key.startswith("multi_detect:")

    # ==========================================================
    # IntentClassificationResult Tests
    # ==========================================================

    def test_intent_classification_result_to_chat_intent(self):
        """IntentClassificationResult → ChatIntent 변환."""
        result = IntentClassificationResult(
            intent=Intent.WASTE,
            confidence=0.95,
            is_complex=True,
        )

        chat_intent = result.to_chat_intent()

        assert chat_intent.intent == Intent.WASTE
        assert chat_intent.confidence == 0.95
        assert chat_intent.complexity == QueryComplexity.COMPLEX

    # ==========================================================
    # Constants Tests
    # ==========================================================

    def test_intent_cache_ttl(self):
        """캐시 TTL 상수."""
        assert INTENT_CACHE_TTL == 3600  # 1시간
