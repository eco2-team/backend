"""Chat Worker Domain Layer.

Chat 고유의 비즈니스 개념을 정의합니다.

- enums: Intent, QueryComplexity, InputType
- value_objects: ChatIntent, HumanInputRequest, HumanInputResponse, LocationData

참고: DisposalRule(scan), Character(character)는
      해당 도메인을 Tool Calling으로 호출합니다.
"""

from chat_worker.domain.enums import InputType, Intent, QueryComplexity
from chat_worker.domain.value_objects import (
    ChatIntent,
    HumanInputRequest,
    HumanInputResponse,
    LocationData,
)

__all__ = [
    # Enums
    "InputType",
    "Intent",
    "QueryComplexity",
    # Value Objects
    "ChatIntent",
    "HumanInputRequest",
    "HumanInputResponse",
    "LocationData",
]
