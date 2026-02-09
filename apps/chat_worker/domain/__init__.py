"""Chat Worker Domain Layer.

Chat 고유의 비즈니스 개념을 정의합니다.

- enums: Intent, QueryComplexity, InputType, EvalGrade
- value_objects: ChatIntent, HumanInputRequest, HumanInputResponse, LocationData,
                 AxisScore, ContinuousScore
- exceptions: DomainError, InvalidBARSScoreError, InvalidGradeError
- services: EvalScoringService

참고: DisposalRule(scan), Character(character)는
      해당 도메인을 Tool Calling으로 호출합니다.
"""

from chat_worker.domain.enums import EvalGrade, InputType, Intent, QueryComplexity
from chat_worker.domain.exceptions import (
    DomainError,
    InvalidBARSScoreError,
    InvalidGradeError,
)
from chat_worker.domain.services import EvalScoringService
from chat_worker.domain.value_objects import (
    AxisScore,
    ChatIntent,
    ContinuousScore,
    HumanInputRequest,
    HumanInputResponse,
    LocationData,
)

__all__ = [
    # Enums
    "EvalGrade",
    "InputType",
    "Intent",
    "QueryComplexity",
    # Value Objects
    "AxisScore",
    "ChatIntent",
    "ContinuousScore",
    "HumanInputRequest",
    "HumanInputResponse",
    "LocationData",
    # Exceptions
    "DomainError",
    "InvalidBARSScoreError",
    "InvalidGradeError",
    # Services
    "EvalScoringService",
]
