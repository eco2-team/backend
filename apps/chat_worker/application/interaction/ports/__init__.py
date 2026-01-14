"""Interaction Ports - HITL 추상화.

- InputRequesterPort: 입력 요청 발행
- InteractionStateStorePort: 상태 저장/조회 (SoT 분리)
"""

from chat_worker.application.interaction.ports.input_requester import (
    InputRequesterPort,
)
from chat_worker.application.interaction.ports.interaction_state_store import (
    InteractionStateStorePort,
)

__all__ = [
    "InputRequesterPort",
    "InteractionStateStorePort",
]
