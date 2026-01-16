"""LangSmith Telemetry Adapter - TelemetryConfigPort 구현.

Infrastructure Layer에서 TelemetryConfigPort를 LangSmith로 구현합니다.
Application Layer는 LangSmith를 직접 알지 않고 TelemetryConfigPort만 사용.
"""

from __future__ import annotations

from typing import Any

from chat_worker.application.ports.telemetry import TelemetryConfigPort
from chat_worker.infrastructure.telemetry.langsmith import (
    get_run_config,
    is_langsmith_enabled,
)


class LangSmithTelemetryAdapter(TelemetryConfigPort):
    """LangSmith Telemetry 어댑터.

    TelemetryConfigPort를 LangSmith로 구현합니다.
    Application Layer에서는 TelemetryConfigPort 타입으로만 주입받습니다.

    사용 예시:
        telemetry = LangSmithTelemetryAdapter()
        command = ProcessChatCommand(
            pipeline=graph,
            progress_notifier=notifier,
            telemetry=telemetry,
        )
    """

    def __init__(self, default_tags: list[str] | None = None):
        """초기화.

        Args:
            default_tags: 모든 요청에 추가할 기본 태그 (예: ["env:production"])
        """
        self._default_tags = default_tags

    def is_enabled(self) -> bool:
        """LangSmith 활성화 여부 확인."""
        return is_langsmith_enabled()

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

        LangSmith의 get_run_config를 래핑하여 기본 태그를 추가합니다.
        """
        # 기본 태그와 요청별 태그 병합
        merged_tags: list[str] = []
        if self._default_tags:
            merged_tags.extend(self._default_tags)
        if tags:
            merged_tags.extend(tags)

        return get_run_config(
            job_id=job_id,
            session_id=session_id,
            user_id=user_id,
            intent=intent,
            tags=merged_tags if merged_tags else None,
            metadata=metadata,
        )


__all__ = ["LangSmithTelemetryAdapter"]
