"""Progress Notifier Port - SSE/UI 진행률 알림.

사용자에게 파이프라인 진행 상황을 실시간으로 전달.

책임:
- 단계별 진행 이벤트 (intent, rag, answer)
- 토큰 스트리밍 (답변 생성 중)
- Human-in-the-Loop 입력 요청 (needs_input)

vs DomainEventBus:
- ProgressNotifier: 사용자 피드백 (SSE → Frontend)
- DomainEventBus: 시스템 연동 (MQ → 다른 서비스)
"""

from abc import ABC, abstractmethod
from typing import Any


class ProgressNotifierPort(ABC):
    """진행률 알림 포트.

    SSE를 통해 Frontend에 진행 상황 전달.
    Redis Streams → event_router → Redis Pub/Sub → SSE Gateway
    """

    @abstractmethod
    async def notify_stage(
        self,
        task_id: str,
        stage: str,
        status: str,
        progress: int | None = None,
        result: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> str:
        """단계 이벤트 발행.

        Args:
            task_id: 작업 ID
            stage: 단계 (queued, intent, rag, answer, done)
            status: 상태 (started, processing, completed, failed)
            progress: 진행률 (0-100)
            result: 단계 결과
            message: 사용자에게 표시할 메시지

        Returns:
            이벤트 ID
        """
        pass

    @abstractmethod
    async def notify_token(
        self,
        task_id: str,
        content: str,
    ) -> str:
        """토큰 스트리밍 이벤트 발행.

        답변 생성 중 실시간 토큰 전달.

        Args:
            task_id: 작업 ID
            content: 토큰 내용

        Returns:
            이벤트 ID
        """
        pass

    @abstractmethod
    async def notify_needs_input(
        self,
        task_id: str,
        input_type: str,
        message: str,
        timeout: int = 60,
    ) -> str:
        """Human-in-the-Loop 입력 요청 이벤트 발행.

        사용자에게 추가 입력을 요청.
        Frontend가 입력 수집 후 POST /chat/{job_id}/input으로 전달.

        Args:
            task_id: 작업 ID
            input_type: 입력 타입 (location, confirmation 등)
            message: 사용자에게 표시할 메시지
            timeout: 입력 대기 시간 (초)

        Returns:
            이벤트 ID
        """
        pass

    @abstractmethod
    async def notify_token_v2(
        self,
        task_id: str,
        content: str,
        node: str | None = None,
    ) -> str:
        """토큰 스트리밍 이벤트 발행 (복구 가능).

        LangGraph 네이티브 스트리밍과 통합.
        Token Stream + Token State 저장으로 재연결 시 복구 지원.

        Args:
            task_id: 작업 ID
            content: 토큰 내용
            node: 토큰 발생 노드명 (answer, summarize 등)

        Returns:
            이벤트 ID
        """
        pass

    @abstractmethod
    async def finalize_token_stream(self, task_id: str) -> None:
        """토큰 스트림 완료 처리.

        토큰 스트리밍 완료 시 최종 State 저장 및 메모리 정리.

        Args:
            task_id: 작업 ID
        """
        pass

    @abstractmethod
    def clear_token_counter(self, task_id: str) -> None:
        """토큰 카운터 정리.

        작업 완료 시 메모리 정리.

        Args:
            task_id: 작업 ID
        """
        pass
