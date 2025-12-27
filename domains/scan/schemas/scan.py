from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl

from domains._shared.schemas.waste import WasteClassificationResult
from domains.character.schemas.reward import CharacterRewardResponse


class ClassificationRequest(BaseModel):
    """폐기물 분류 요청.

    동기 처리: POST /scan/classify
    스트리밍: POST /scan/classify/completion (SSE)
    """

    image_url: Optional[HttpUrl] = Field(
        default=None,
        description="분석할 단일 이미지 URL",
    )
    user_input: Optional[str] = Field(
        default=None,
        description="사용자 질문/설명 (없으면 기본 안내 문구 사용)",
    )


class ClassificationResponse(BaseModel):
    """분류 응답 (동기 처리 결과)."""

    task_id: str
    status: str
    message: Optional[str] = None
    pipeline_result: Optional[WasteClassificationResult] = None
    reward: Optional[CharacterRewardResponse] = None
    error: Optional[str] = None


class ScanSubmitResponse(BaseModel):
    """비동기 스캔 제출 응답.

    클라이언트 흐름:
    1. POST /api/v1/scan → 이 응답 수신
    2. GET {stream_url} → SSE 스트리밍 구독
    3. GET {result_url} → 최종 결과 조회
    """

    job_id: str = Field(description="작업 ID (UUID)")
    stream_url: str = Field(description="SSE 스트리밍 URL")
    result_url: str = Field(description="결과 조회 URL")
    status: str = Field(default="queued", description="현재 상태")


class ScanProcessingResponse(BaseModel):
    """처리 중 응답 (202 Accepted).

    결과가 아직 준비되지 않았을 때 반환됩니다.
    클라이언트는 Retry-After 헤더를 확인하고 재시도해야 합니다.
    """

    status: str = Field(default="processing", description="처리 상태")
    message: str = Field(default="결과 준비 중입니다.", description="상태 메시지")
    current_stage: Optional[str] = Field(None, description="현재 처리 단계")
    progress: Optional[int] = Field(None, description="진행률 (0-100)")


class ScanTask(BaseModel):
    """DEPRECATED: 로그 기반으로 전환됨. 추후 ES → DB 변환 시 사용."""

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
