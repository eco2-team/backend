"""Node Contracts - Single Source of Truth for Field Requirements.

노드 출력 필드와 Intent 요구 필드의 단일 정의.

설계 원칙:
1. Single Source of Truth = INTENT_REQUIRED_FIELDS (필드 요구사항)
2. 노드는 output contract(NODE_OUTPUT_FIELDS)를 선언
3. is_required는 파생값: node outputs ∩ required fields ≠ ∅

이 파일이 답해야 하는 질문:
- "waste 답변을 만들려면 어떤 필드가 필요하지?" → INTENT_REQUIRED_FIELDS["waste"]
- "그 필드를 누가 만들지?" → FIELD_TO_NODES["disposal_rules"]
- "이 노드는 필수야?" → is_node_required("waste_rag", "waste")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

# ============================================================
# Node Output Contracts
# ============================================================

NODE_OUTPUT_FIELDS: dict[str, frozenset[str]] = {
    # 필수 노드들
    "waste_rag": frozenset({"disposal_rules"}),
    "bulk_waste": frozenset({"bulk_waste_context"}),
    "location": frozenset({"location_context"}),
    "general": frozenset({"general_context"}),
    # 선택 노드들
    "character": frozenset({"character_context"}),
    "weather": frozenset({"weather_context"}),
    "collection_point": frozenset({"collection_point_context"}),
    "web_search": frozenset({"web_search_results"}),
    "recyclable_price": frozenset({"recyclable_price_context"}),
    "image_generation": frozenset({"image_url", "image_description"}),
}
"""노드별 출력 필드.

각 노드가 state에 기록하는 필드 목록.
NodeResult.outputs의 키와 일치해야 함.
"""


# ============================================================
# Intent Required Fields
# ============================================================

INTENT_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "waste": frozenset({"disposal_rules"}),
    "bulk_waste": frozenset({"bulk_waste_context"}),
    "location": frozenset({"location_context"}),
    "collection_point": frozenset({"collection_point_context"}),
    "general": frozenset(),  # LLM 직접 응답, 별도 컨텍스트 불필요
    # 선택 intent (FAIL_OPEN)
    "character": frozenset(),
    "weather": frozenset(),
    "web_search": frozenset(),
    "recyclable_price": frozenset(),
    "image_generation": frozenset(),
}
"""Intent별 필수 필드.

해당 intent 답변 생성에 반드시 필요한 필드.
누락 시 fallback 트리거.
"""


INTENT_OPTIONAL_FIELDS: dict[str, frozenset[str]] = {
    "waste": frozenset({"character_context", "weather_context"}),
    "bulk_waste": frozenset({"weather_context"}),
    "location": frozenset({"weather_context"}),
    "collection_point": frozenset({"weather_context"}),
    "general": frozenset({"web_search_results"}),
    "character": frozenset(),
    "weather": frozenset(),
    "web_search": frozenset(),
    "recyclable_price": frozenset(),
    "image_generation": frozenset(),
}
"""Intent별 선택 필드.

있으면 답변 품질 향상, 없어도 답변 가능.
"""


# ============================================================
# Derived Mappings (Computed at import time)
# ============================================================

def _build_field_to_nodes() -> dict[str, frozenset[str]]:
    """필드 → 생산 노드 역매핑 생성."""
    result: dict[str, set[str]] = {}
    for node, fields in NODE_OUTPUT_FIELDS.items():
        for field in fields:
            if field not in result:
                result[field] = set()
            result[field].add(node)
    return {k: frozenset(v) for k, v in result.items()}


FIELD_TO_NODES: dict[str, frozenset[str]] = _build_field_to_nodes()
"""필드 → 생산 노드 매핑.

"disposal_rules 필드를 누가 만들지?" → FIELD_TO_NODES["disposal_rules"]
"""


# ============================================================
# Helper Functions
# ============================================================


def get_required_fields(intent: str) -> frozenset[str]:
    """Intent의 필수 필드 조회.

    Args:
        intent: 의도 문자열

    Returns:
        필수 필드 집합 (없으면 빈 집합)
    """
    return INTENT_REQUIRED_FIELDS.get(intent, frozenset())


def get_optional_fields(intent: str) -> frozenset[str]:
    """Intent의 선택 필드 조회."""
    return INTENT_OPTIONAL_FIELDS.get(intent, frozenset())


def get_producing_nodes(field: str) -> frozenset[str]:
    """필드를 생산하는 노드 조회.

    Args:
        field: 필드명

    Returns:
        생산 노드 집합 (없으면 빈 집합)
    """
    return FIELD_TO_NODES.get(field, frozenset())


def is_node_required_for_intent(node_name: str, intent: str) -> bool:
    """노드가 해당 Intent에서 필수인지 판단.

    is_required = (node outputs ∩ intent required fields) ≠ ∅

    Args:
        node_name: 노드 이름
        intent: 의도 문자열

    Returns:
        필수 여부
    """
    node_outputs = NODE_OUTPUT_FIELDS.get(node_name, frozenset())
    required_fields = INTENT_REQUIRED_FIELDS.get(intent, frozenset())
    return bool(node_outputs & required_fields)


def get_required_nodes_for_intent(intent: str) -> frozenset[str]:
    """Intent에 필요한 필수 노드 목록.

    Args:
        intent: 의도 문자열

    Returns:
        필수 노드 집합
    """
    required_fields = INTENT_REQUIRED_FIELDS.get(intent, frozenset())
    required_nodes: set[str] = set()
    for field in required_fields:
        nodes = FIELD_TO_NODES.get(field, frozenset())
        required_nodes.update(nodes)
    return frozenset(required_nodes)


def validate_missing_fields(
    intent: str,
    collected_fields: set[str],
) -> tuple[frozenset[str], frozenset[str]]:
    """누락된 필수/선택 필드 검증.

    Args:
        intent: 의도 문자열
        collected_fields: 수집된 필드 집합

    Returns:
        (missing_required, missing_optional) 튜플
    """
    required = INTENT_REQUIRED_FIELDS.get(intent, frozenset())
    optional = INTENT_OPTIONAL_FIELDS.get(intent, frozenset())

    missing_required = required - collected_fields
    missing_optional = optional - collected_fields

    return frozenset(missing_required), frozenset(missing_optional)


# ============================================================
# Validation (Import-time check)
# ============================================================


@dataclass(frozen=True)
class ContractValidationResult:
    """Contract 검증 결과."""
    is_valid: bool
    errors: tuple[str, ...]


def validate_contracts() -> ContractValidationResult:
    """모든 Contract 일관성 검증.

    검증 항목:
    1. 모든 INTENT_REQUIRED_FIELDS의 필드가 어떤 노드에서 생산되는지
    2. 모든 INTENT_OPTIONAL_FIELDS의 필드가 어떤 노드에서 생산되는지

    Returns:
        검증 결과
    """
    errors: list[str] = []

    # 1. Required fields 검증
    for intent, required_fields in INTENT_REQUIRED_FIELDS.items():
        for field in required_fields:
            if field not in FIELD_TO_NODES:
                errors.append(
                    f"Intent '{intent}' requires field '{field}' "
                    f"but no node produces it"
                )

    # 2. Optional fields 검증
    for intent, optional_fields in INTENT_OPTIONAL_FIELDS.items():
        for field in optional_fields:
            if field not in FIELD_TO_NODES:
                errors.append(
                    f"Intent '{intent}' optionally uses field '{field}' "
                    f"but no node produces it"
                )

    return ContractValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
    )


# Import-time validation
_validation_result = validate_contracts()
if not _validation_result.is_valid:
    import warnings
    for error in _validation_result.errors:
        warnings.warn(f"Contract validation error: {error}", stacklevel=2)


__all__ = [
    "FIELD_TO_NODES",
    "INTENT_OPTIONAL_FIELDS",
    "INTENT_REQUIRED_FIELDS",
    "NODE_OUTPUT_FIELDS",
    "ContractValidationResult",
    "get_optional_fields",
    "get_producing_nodes",
    "get_required_fields",
    "get_required_nodes_for_intent",
    "is_node_required_for_intent",
    "validate_contracts",
    "validate_missing_fields",
]
