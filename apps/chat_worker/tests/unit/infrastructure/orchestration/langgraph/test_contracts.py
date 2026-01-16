"""Contract 검증 테스트.

contracts.py의 정적 검증을 테스트합니다.
CI에서 실행되어 필드 불일치를 조기에 발견합니다.

테스트 항목:
1. 모든 필수 필드가 생산 가능한지
2. 모든 선택 필드가 생산 가능한지
3. is_node_required_for_intent 동작
4. validate_missing_fields 동작
"""

from __future__ import annotations

import pytest

from chat_worker.infrastructure.orchestration.langgraph.contracts import (
    FIELD_TO_NODES,
    INTENT_OPTIONAL_FIELDS,
    INTENT_REQUIRED_FIELDS,
    get_producing_nodes,
    get_required_nodes_for_intent,
    is_node_required_for_intent,
    validate_contracts,
    validate_missing_fields,
)


class TestContractValidation:
    """Contract 정적 검증."""

    def test_validate_contracts_passes(self) -> None:
        """모든 필수/선택 필드가 생산 가능해야 함."""
        result = validate_contracts()

        assert result.is_valid, f"Contract validation failed: {result.errors}"
        assert len(result.errors) == 0

    def test_all_required_fields_have_producers(self) -> None:
        """모든 Intent의 필수 필드가 생산 노드를 가져야 함."""
        for intent, required_fields in INTENT_REQUIRED_FIELDS.items():
            for field in required_fields:
                producers = get_producing_nodes(field)
                assert len(producers) > 0, (
                    f"Intent '{intent}' requires field '{field}' "
                    f"but no node produces it"
                )

    def test_all_optional_fields_have_producers(self) -> None:
        """모든 Intent의 선택 필드가 생산 노드를 가져야 함."""
        for intent, optional_fields in INTENT_OPTIONAL_FIELDS.items():
            for field in optional_fields:
                producers = get_producing_nodes(field)
                assert len(producers) > 0, (
                    f"Intent '{intent}' optionally uses field '{field}' "
                    f"but no node produces it"
                )


class TestIsNodeRequiredForIntent:
    """is_node_required_for_intent 함수 테스트."""

    @pytest.mark.parametrize(
        ("node_name", "intent", "expected"),
        [
            # waste_rag는 waste intent에서 필수
            ("waste_rag", "waste", True),
            # waste_rag는 general intent에서 불필요
            ("waste_rag", "general", False),
            # bulk_waste는 bulk_waste intent에서 필수
            ("bulk_waste", "bulk_waste", True),
            # character는 어느 intent에서도 필수가 아님
            ("character", "waste", False),
            ("character", "general", False),
            # location은 location intent에서 필수
            ("location", "location", True),
            # 알 수 없는 노드/intent는 False
            ("unknown_node", "waste", False),
            ("waste_rag", "unknown_intent", False),
        ],
    )
    def test_is_node_required_for_intent(
        self,
        node_name: str,
        intent: str,
        expected: bool,
    ) -> None:
        """노드-Intent 필수 관계 검증."""
        assert is_node_required_for_intent(node_name, intent) == expected


class TestValidateMissingFields:
    """validate_missing_fields 함수 테스트."""

    def test_all_required_collected(self) -> None:
        """모든 필수 필드가 수집되면 누락 없음."""
        collected = {"disposal_rules", "character_context", "weather_context"}
        missing_required, missing_optional = validate_missing_fields(
            intent="waste",
            collected_fields=collected,
        )

        assert len(missing_required) == 0
        assert len(missing_optional) == 0

    def test_missing_required_field(self) -> None:
        """필수 필드 누락 감지."""
        collected = {"character_context"}  # disposal_rules 누락
        missing_required, missing_optional = validate_missing_fields(
            intent="waste",
            collected_fields=collected,
        )

        assert "disposal_rules" in missing_required
        # character_context, weather_context는 선택
        assert "character_context" not in missing_optional
        assert "weather_context" in missing_optional

    def test_missing_optional_field(self) -> None:
        """선택 필드 누락 감지."""
        collected = {"disposal_rules"}  # 필수는 있고 선택 없음
        missing_required, missing_optional = validate_missing_fields(
            intent="waste",
            collected_fields=collected,
        )

        assert len(missing_required) == 0
        assert "character_context" in missing_optional
        assert "weather_context" in missing_optional

    def test_general_intent_no_required(self) -> None:
        """general intent는 필수 필드 없음."""
        collected: set[str] = set()
        missing_required, _ = validate_missing_fields(
            intent="general",
            collected_fields=collected,
        )

        assert len(missing_required) == 0


class TestGetRequiredNodesForIntent:
    """get_required_nodes_for_intent 함수 테스트."""

    def test_waste_intent_requires_waste_rag(self) -> None:
        """waste intent는 waste_rag 노드 필요."""
        required_nodes = get_required_nodes_for_intent("waste")

        assert "waste_rag" in required_nodes

    def test_bulk_waste_intent_requires_bulk_waste(self) -> None:
        """bulk_waste intent는 bulk_waste 노드 필요."""
        required_nodes = get_required_nodes_for_intent("bulk_waste")

        assert "bulk_waste" in required_nodes

    def test_general_intent_no_required_nodes(self) -> None:
        """general intent는 필수 노드 없음."""
        required_nodes = get_required_nodes_for_intent("general")

        assert len(required_nodes) == 0


class TestFieldToNodes:
    """FIELD_TO_NODES 역매핑 테스트."""

    def test_disposal_rules_produced_by_waste_rag(self) -> None:
        """disposal_rules는 waste_rag에서 생산."""
        assert "waste_rag" in FIELD_TO_NODES.get("disposal_rules", frozenset())

    def test_character_context_produced_by_character(self) -> None:
        """character_context는 character에서 생산."""
        assert "character" in FIELD_TO_NODES.get("character_context", frozenset())

    def test_unknown_field_returns_empty(self) -> None:
        """알 수 없는 필드는 빈 집합."""
        assert get_producing_nodes("unknown_field") == frozenset()
