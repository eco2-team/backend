"""Interaction - Human-in-the-Loop.

사용자 추가 입력 요청 및 처리.

설계 원칙:
- Application은 "이벤트 발행 + 상태 저장"까지만
- 실제 "대기/재개(resume)"는 Infrastructure/Presentation에서 처리

SoT 분리:
- InputRequesterPort: 이벤트 발행
- InteractionStateStorePort: 상태 저장/조회

이 분리로:
- 테스트 용이 (blocking wait 없음)
- 타임아웃 설계 단순화
- 운영 안정성 향상
"""

from chat_worker.application.interaction.ports import (
    InputRequesterPort,
    InteractionStateStorePort,
)
from chat_worker.application.interaction.services import HumanInteractionService

__all__ = [
    "InputRequesterPort",
    "InteractionStateStorePort",
    "HumanInteractionService",
]
