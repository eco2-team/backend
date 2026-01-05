"""Pipeline Stage Enum."""

from enum import Enum


class PipelineStage(str, Enum):
    """파이프라인 단계.

    SSE 이벤트 스키마와 일치해야 함.
    """

    QUEUED = "queued"
    VISION = "vision"
    RULE = "rule"
    ANSWER = "answer"
    REWARD = "reward"
    DONE = "done"

    @property
    def progress(self) -> int:
        """단계별 진행률 반환."""
        return _STAGE_PROGRESS_MAP.get(self, 0)


# 단계별 진행률 매핑 (SSE 호환)
_STAGE_PROGRESS_MAP: dict[PipelineStage, int] = {
    PipelineStage.QUEUED: 0,
    PipelineStage.VISION: 25,
    PipelineStage.RULE: 50,
    PipelineStage.ANSWER: 75,
    PipelineStage.REWARD: 100,
    PipelineStage.DONE: 100,
}
