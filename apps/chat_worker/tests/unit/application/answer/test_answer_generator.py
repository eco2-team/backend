"""AnswerGeneratorService 단위 테스트.

Clean Architecture 리팩토링 후:
- Service: 순수 비즈니스 로직 (프롬프트 생성, 유효성 검증)
- Command: LLM 호출, 오케스트레이션 (GenerateAnswerCommand에서 테스트)
"""

from __future__ import annotations

import pytest

from chat_worker.application.dto.answer_context import AnswerContext
from chat_worker.application.services.answer_generator import AnswerGeneratorService


class TestAnswerGeneratorService:
    """AnswerGeneratorService 테스트 스위트."""

    @pytest.fixture
    def service(self) -> AnswerGeneratorService:
        """테스트용 서비스 (순수 로직, Port 의존 없음)."""
        return AnswerGeneratorService()

    @pytest.fixture
    def simple_context(self) -> AnswerContext:
        """간단한 컨텍스트."""
        return AnswerContext(
            user_input="페트병 어떻게 버려?",
        )

    @pytest.fixture
    def full_context(self) -> AnswerContext:
        """전체 컨텍스트."""
        return AnswerContext(
            classification={"major_category": "재활용", "minor_category": "페트병"},
            disposal_rules={"method": "라벨 제거 후 분리수거"},
            character_context={"name": "페트리", "dialog": "재활용해줘서 고마워!"},
            location_context={"found": True, "count": 3},
            user_input="페트병 어떻게 버려?",
        )

    # ==========================================================
    # build_prompt Tests
    # ==========================================================

    def test_build_prompt_simple(
        self,
        service: AnswerGeneratorService,
        simple_context: AnswerContext,
    ):
        """간단한 컨텍스트로 프롬프트 생성."""
        prompt = service.build_prompt(simple_context)

        assert len(prompt) > 0
        assert "페트병" in prompt

    def test_build_prompt_with_full_context(
        self,
        service: AnswerGeneratorService,
        full_context: AnswerContext,
    ):
        """전체 컨텍스트로 프롬프트 생성."""
        prompt = service.build_prompt(full_context)

        assert len(prompt) > 0
        # 컨텍스트 정보가 포함되었는지 확인
        assert "페트병" in prompt or "재활용" in prompt

    # ==========================================================
    # validate_context Tests
    # ==========================================================

    def test_validate_context_valid(
        self,
        service: AnswerGeneratorService,
        simple_context: AnswerContext,
    ):
        """유효한 컨텍스트 검증."""
        assert service.validate_context(simple_context)

    def test_validate_context_empty_input(
        self,
        service: AnswerGeneratorService,
    ):
        """빈 입력은 유효하지 않음."""
        context = AnswerContext(user_input="")
        assert not service.validate_context(context)

    def test_validate_context_whitespace_only(
        self,
        service: AnswerGeneratorService,
    ):
        """공백만 있는 입력은 유효하지 않음."""
        context = AnswerContext(user_input="   ")
        assert not service.validate_context(context)

    # ==========================================================
    # should_use_streaming Tests
    # ==========================================================

    def test_should_use_streaming_with_context(
        self,
        service: AnswerGeneratorService,
        full_context: AnswerContext,
    ):
        """컨텍스트가 있으면 스트리밍 권장."""
        assert service.should_use_streaming(full_context)

    def test_should_use_streaming_long_input(
        self,
        service: AnswerGeneratorService,
    ):
        """긴 입력이면 스트리밍 권장."""
        context = AnswerContext(
            user_input="이것은 50자가 넘는 아주 긴 사용자 입력입니다. 분리배출에 대해 자세히 알려주세요. 추가 질문도 있습니다."
        )
        assert service.should_use_streaming(context)

    def test_should_use_streaming_short_simple(
        self,
        service: AnswerGeneratorService,
    ):
        """짧은 단순 입력은 스트리밍 불필요."""
        context = AnswerContext(user_input="안녕")
        assert not service.should_use_streaming(context)

    # ==========================================================
    # Factory Method Tests
    # ==========================================================

    def test_create_context_minimal(self):
        """최소 컨텍스트 생성."""
        context = AnswerGeneratorService.create_context(
            user_input="테스트",
        )

        assert context.user_input == "테스트"
        assert context.classification is None
        assert context.disposal_rules is None

    def test_create_context_full(self):
        """전체 컨텍스트 생성."""
        context = AnswerGeneratorService.create_context(
            classification={"key": "value"},
            disposal_rules={"rule": "test"},
            character_context={"name": "테스트"},
            location_context={"found": True},
            user_input="테스트 질문",
        )

        assert context.classification == {"key": "value"}
        assert context.disposal_rules == {"rule": "test"}
        assert context.character_context == {"name": "테스트"}
        assert context.location_context == {"found": True}
        assert context.user_input == "테스트 질문"

    def test_create_context_with_web_search(self):
        """웹 검색 결과 포함 컨텍스트 생성."""
        context = AnswerGeneratorService.create_context(
            web_search_results={"query": "테스트", "results": []},
            user_input="최신 정책",
        )

        assert context.web_search_results == {"query": "테스트", "results": []}


class TestAnswerContext:
    """AnswerContext DTO 테스트."""

    def test_to_prompt_context_with_user_input_only(self):
        """사용자 입력만 있는 경우."""
        context = AnswerContext(user_input="질문입니다")

        prompt = context.to_prompt_context()

        assert "질문입니다" in prompt

    def test_to_prompt_context_with_classification(self):
        """분류 정보 포함."""
        context = AnswerContext(
            classification={"major_category": "재활용"},
            user_input="질문",
        )

        prompt = context.to_prompt_context()

        assert "재활용" in prompt

    def test_to_prompt_context_with_disposal_rules(self):
        """분리배출 규칙 포함."""
        context = AnswerContext(
            disposal_rules={"method": "세척 후 배출"},
            user_input="질문",
        )

        prompt = context.to_prompt_context()

        assert "세척" in prompt

    def test_has_context_true(self):
        """컨텍스트 존재 확인."""
        context = AnswerContext(
            classification={"key": "value"},
            user_input="질문",
        )

        assert context.has_context()

    def test_has_context_false(self):
        """컨텍스트 없음 확인."""
        context = AnswerContext(user_input="질문")

        assert not context.has_context()

    def test_to_prompt_context_with_web_search_results(self):
        """웹 검색 결과 포함."""
        context = AnswerContext(
            web_search_results="최신 정책: 2026년부터 플라스틱 규제 강화",
            user_input="최신 정책 알려줘",
        )

        prompt = context.to_prompt_context()

        assert "2026년" in prompt or "플라스틱" in prompt

    def test_to_prompt_context_with_all_fields(self):
        """모든 필드 포함."""
        context = AnswerContext(
            classification={"major_category": "재활용"},
            disposal_rules={"method": "세척 후 배출"},
            character_context={"name": "페트리"},
            location_context={"found": True},
            web_search_results="최신 정보",
            user_input="질문",
        )

        prompt = context.to_prompt_context()

        assert "재활용" in prompt
        assert "세척" in prompt
        assert "질문" in prompt
