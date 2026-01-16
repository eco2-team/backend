"""Telemetry Port - Observability 설정 추상화.

Application Layer에서 LangSmith 등 Observability 플랫폼에
직접 의존하지 않고 Port를 통해 설정을 주입받습니다.

Clean Architecture:
- Application Layer는 이 Port만 사용
- Infrastructure Layer에서 LangSmith 등으로 구현
"""

from __future__ import annotations

from typing import Any, Protocol


class TelemetryConfigPort(Protocol):
    """Telemetry 설정 생성 Port.

    LangGraph 실행 시 필요한 Observability 설정을 생성합니다.
    LangSmith, OpenTelemetry 등 다양한 구현체가 가능합니다.

    Usage:
        class ProcessChatCommand:
            def __init__(self, telemetry: TelemetryConfigPort | None = None):
                self._telemetry = telemetry

            async def execute(self, request):
                config = {}
                if self._telemetry:
                    config = self._telemetry.get_run_config(
                        job_id=request.job_id,
                        session_id=request.session_id,
                        user_id=request.user_id,
                    )
                result = await self._pipeline.ainvoke(state, config=config)
    """

    def is_enabled(self) -> bool:
        """Telemetry 활성화 여부.

        Returns:
            True if telemetry is enabled and configured
        """
        ...

    def get_run_config(
        self,
        job_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        intent: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LangGraph 실행을 위한 config 생성.

        Args:
            job_id: 작업 ID (run_name으로 사용)
            session_id: 세션 ID (thread_id로 사용, 멀티턴 대화 연결)
            user_id: 사용자 ID (메타데이터)
            intent: 분류된 Intent (태그 및 메타데이터)
            tags: 추가 태그
            metadata: 추가 메타데이터

        Returns:
            LangGraph compatible config dict
        """
        ...


class NoOpTelemetryConfig:
    """NoOp Telemetry 설정.

    Telemetry가 비활성화된 경우 사용하는 기본 구현체.
    테스트 환경이나 Telemetry가 필요 없는 경우에 사용.
    """

    def is_enabled(self) -> bool:
        """항상 False 반환."""
        return False

    def get_run_config(
        self,
        job_id: str,
        session_id: str | None = None,
        user_id: str | None = None,
        intent: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """기본 config 반환 (thread_id만 설정)."""
        config: dict[str, Any] = {"configurable": {}}

        if session_id:
            config["configurable"]["thread_id"] = session_id

        return config


__all__ = ["TelemetryConfigPort", "NoOpTelemetryConfig"]
