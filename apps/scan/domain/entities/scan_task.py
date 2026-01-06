"""Scan Task Entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from scan.domain.enums import PipelineStage, TaskStatus
from scan.domain.value_objects import Classification, PipelineResult


@dataclass(slots=True)
class ScanTask:
    """스캔 작업 엔티티.

    Attributes:
        task_id: 작업 고유 식별자 (UUID)
        user_id: 요청 사용자 ID
        image_url: 분석 대상 이미지 URL
        user_input: 사용자 입력 질문/설명
        status: 작업 상태
        current_stage: 현재 파이프라인 단계
        classification: Vision 분류 결과
        pipeline_result: 파이프라인 실행 결과
        reward: 보상 정보
        metadata: 추가 메타데이터 (duration 등)
        created_at: 생성 시각
    """

    task_id: str
    user_id: str
    image_url: str
    user_input: str | None = None
    status: TaskStatus = TaskStatus.QUEUED
    current_stage: PipelineStage = PipelineStage.QUEUED
    classification: Classification | None = None
    pipeline_result: PipelineResult | None = None
    reward: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def progress(self) -> int:
        """현재 진행률 반환."""
        return self.current_stage.progress

    @property
    def is_completed(self) -> bool:
        """작업 완료 여부."""
        return self.status == TaskStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """작업 실패 여부."""
        return self.status == TaskStatus.FAILED

    def advance_stage(self, stage: PipelineStage) -> None:
        """파이프라인 단계 진행."""
        self.current_stage = stage
        self.status = TaskStatus.PROCESSING

    def complete(
        self,
        pipeline_result: PipelineResult,
        reward: dict[str, Any] | None = None,
    ) -> None:
        """작업 완료 처리."""
        self.status = TaskStatus.COMPLETED
        self.current_stage = PipelineStage.DONE
        self.pipeline_result = pipeline_result
        self.reward = reward

    def fail(self, error: str) -> None:
        """작업 실패 처리."""
        self.status = TaskStatus.FAILED
        self.metadata["error"] = error

    def set_classification(self, classification_result: dict[str, Any]) -> None:
        """Vision 분류 결과 설정."""
        self.classification = Classification.from_dict(classification_result)

    def should_attempt_reward(self) -> bool:
        """리워드 평가 조건 확인.

        조건:
        1. 분류 결과가 '재활용폐기물'
        2. 배출 규정이 존재
        3. 답변에 부족한 점이 없음
        """
        if not self.classification:
            return False

        if not self.classification.is_rewardable:
            return False

        if not self.pipeline_result:
            return False

        if not self.pipeline_result.has_disposal_rules:
            return False

        if self.pipeline_result.has_insufficiencies:
            return False

        return True

    def to_submit_response(self, base_url: str = "") -> dict[str, Any]:
        """제출 응답 형식으로 변환.

        Args:
            base_url: API base URL (stream_url, result_url 생성용)
        """
        return {
            "job_id": self.task_id,
            "stream_url": f"{base_url}/api/v1/scan/{self.task_id}/events",
            "result_url": f"{base_url}/api/v1/scan/{self.task_id}/result",
            "status": self.status.value,
        }

    def to_result_response(self) -> dict[str, Any]:
        """결과 응답 형식으로 변환."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "message": "classification completed" if self.is_completed else None,
            "pipeline_result": self.pipeline_result.to_dict() if self.pipeline_result else None,
            "reward": self.reward,
            "error": self.metadata.get("error"),
        }
