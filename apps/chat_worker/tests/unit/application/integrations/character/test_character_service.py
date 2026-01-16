"""CharacterService 단위 테스트.

CharacterService는 순수 로직만 담당 (Port 의존 없음):
- to_answer_context: 컨텍스트 변환
- validate_character: 캐릭터 검증
- build_not_found_context: 캐릭터 없음 컨텍스트
- build_found_context: 캐릭터 찾음 컨텍스트
"""

from __future__ import annotations

import pytest

from chat_worker.application.ports.character_client import CharacterDTO
from chat_worker.application.services.character_service import CharacterService


class TestCharacterService:
    """CharacterService 테스트 스위트 (순수 로직)."""

    @pytest.fixture
    def sample_character(self) -> CharacterDTO:
        """샘플 캐릭터."""
        return CharacterDTO(
            name="페트리",
            type_label="재활용",
            dialog="재활용해줘서 고마워!",
            match_label="플라스틱",
        )

    # ==========================================================
    # to_answer_context Tests
    # ==========================================================

    def test_to_answer_context(self, sample_character: CharacterDTO):
        """컨텍스트 변환."""
        context = CharacterService.to_answer_context(sample_character)

        assert context["name"] == "페트리"
        assert context["type"] == "재활용"
        assert context["dialog"] == "재활용해줘서 고마워!"
        assert context["match_reason"] == "플라스틱"

    def test_to_answer_context_with_none_match_label(self):
        """match_label이 None인 경우."""
        character = CharacterDTO(
            name="테스트",
            type_label="타입",
            dialog="대사",
            match_label=None,
        )

        context = CharacterService.to_answer_context(character)

        assert context["match_reason"] is None

    def test_to_answer_context_structure(self, sample_character: CharacterDTO):
        """컨텍스트 구조 확인."""
        context = CharacterService.to_answer_context(sample_character)

        expected_keys = {"name", "type", "dialog", "match_reason"}
        assert set(context.keys()) == expected_keys

    # ==========================================================
    # validate_character Tests
    # ==========================================================

    def test_validate_character_valid(self, sample_character: CharacterDTO):
        """유효한 캐릭터 검증."""
        assert CharacterService.validate_character(sample_character) is True

    def test_validate_character_none(self):
        """None 캐릭터 검증."""
        assert CharacterService.validate_character(None) is False

    def test_validate_character_empty_name(self):
        """빈 이름 캐릭터 검증."""
        character = CharacterDTO(
            name="",
            type_label="타입",
            dialog="대사",
            match_label="매칭",
        )
        assert CharacterService.validate_character(character) is False

    # ==========================================================
    # build_not_found_context Tests
    # ==========================================================

    def test_build_not_found_context(self):
        """캐릭터 없음 컨텍스트."""
        context = CharacterService.build_not_found_context("플라스틱")

        assert context["waste_category"] == "플라스틱"
        assert context["found"] is False
        assert "찾지 못했어요" in context["message"]

    # ==========================================================
    # build_found_context Tests
    # ==========================================================

    def test_build_found_context(self, sample_character: CharacterDTO):
        """캐릭터 찾음 컨텍스트."""
        context = CharacterService.build_found_context(sample_character, "플라스틱")

        assert context["waste_category"] == "플라스틱"
        assert context["found"] is True
        assert context["name"] == "페트리"
        assert context["type"] == "재활용"
        assert context["dialog"] == "재활용해줘서 고마워!"
        assert context["match_reason"] == "플라스틱"
