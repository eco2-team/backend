from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl

from domains._shared.schemas.waste import WasteClassificationResult
from domains.character.schemas.reward import CharacterRewardResponse


class ClassificationRequest(BaseModel):
    image_url: Optional[HttpUrl] = Field(
        default=None,
        description="분석할 단일 이미지 URL",
    )
    user_input: Optional[str] = Field(
        default=None,
        description="사용자 질문/설명 (없으면 기본 안내 문구 사용)",
    )


class ClassificationResponse(BaseModel):
    task_id: str
    status: str
    message: str
    pipeline_result: Optional[WasteClassificationResult] = None
    reward: Optional[CharacterRewardResponse] = None
    error: Optional[str] = None


class ScanTask(BaseModel):
    task_id: str
    status: str
    category: Optional[str] = None
    confidence: Optional[float] = None
    completed_at: Optional[datetime] = None
    pipeline_result: Optional[WasteClassificationResult] = None
    reward: Optional[CharacterRewardResponse] = None


class ScanCategory(BaseModel):
    id: int
    name: str
    display_name: str
    instructions: List[str]


# ============================================================
# Async API Schemas (Celery + RabbitMQ)
# ============================================================


class AsyncTaskStatus(str, Enum):
    """비동기 태스크 상태."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AsyncTaskStep(str, Enum):
    """파이프라인 단계 (프론트엔드 UI 프로그레스용)."""

    PENDING = "pending"
    SCAN = "scan"  # 확인 (Vision)
    ANALYZE = "analyze"  # 분석 (RAG)
    ANSWER = "answer"  # 배출방법 (Answer)
    COMPLETE = "complete"


class AsyncClassifyResponse(BaseModel):
    """비동기 분류 요청 응답 (202 Accepted)."""

    task_id: str = Field(description="태스크 ID (폴링/SSE 구독용)")
    status: AsyncTaskStatus = Field(default=AsyncTaskStatus.QUEUED)
    message: str = Field(default="분류 작업이 큐에 등록되었습니다.")


class PartialClassificationResult(BaseModel):
    """단계별 부분 결과."""

    classification: Optional[Dict[str, Any]] = Field(
        default=None,
        description="분류 결과 (major/middle/minor category)",
    )
    situation_tags: Optional[List[str]] = Field(
        default=None,
        description="상황 태그",
    )


class AsyncTaskState(BaseModel):
    """비동기 태스크 상태 조회 응답."""

    task_id: str
    status: AsyncTaskStatus
    step: AsyncTaskStep = Field(description="현재 단계 (UI 프로그레스)")
    progress: int = Field(ge=0, le=100, description="진행률 (0-100)")

    # 부분 결과 (단계별)
    partial_result: Optional[PartialClassificationResult] = None

    # 최종 결과 (완료 시)
    result: Optional[WasteClassificationResult] = None

    # 에러 정보 (실패 시)
    error: Optional[str] = None
    error_code: Optional[str] = None

    # 리워드 상태
    reward_status: str = Field(
        default="pending",
        description="리워드 상태 (pending|processing|granted|failed|queued)",
    )

    # 타이밍
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # 메타데이터 (duration 등)
    metadata: Optional[Dict[str, Any]] = None
