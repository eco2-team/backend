"""Event Publisher Port - Redis Streams 이벤트 발행 추상화."""

from abc import ABC, abstractmethod
from typing import Any


class EventPublisherPort(ABC):
    """이벤트 발행 포트 - Redis Streams.

    SSE Gateway와 연동되는 이벤트 발행.
    멱등성 보장 (Lua Script 기반).
    """

    @abstractmethod
    def publish_stage_event(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
    ) -> str:
        """단계 이벤트를 Redis Streams에 발행.

        Args:
            task_id: 작업 ID (UUID)
            stage: 단계명 (queued, vision, rule, answer, reward, done)
            status: 상태 (started, completed, failed)
            progress: 진행률 0~100 (선택)
            result: 완료 시 결과 데이터 (선택)

        Returns:
            발행된 메시지 ID (예: "1735123456789-0")

        Note:
            - Celery Task 재시도 시에도 중복 발행 없음 (멱등성)
            - Event Router가 Streams → Pub/Sub로 중계
            - SSE Gateway가 Pub/Sub → 클라이언트로 전달
        """
        pass
