from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl

from domains._shared.schemas.waste import WasteClassificationResult
from domains.character.schemas.reward import CharacterRewardResponse


class ClassificationRequest(BaseModel):
    """폐기물 분류 요청.

    비동기 처리:
        POST /scan/classify/async 사용 시 task_id가 즉시 반환되며,
        GET /scan/{task_id}/progress (SSE)로 진행상황 및 최종 결과를 수신합니다.
    """

    image_url: Optional[HttpUrl] = Field(
        default=None,
        description="분석할 단일 이미지 URL",
    )
    user_input: Optional[str] = Field(
        default=None,
        description="사용자 질문/설명 (없으면 기본 안내 문구 사용)",
    )
    callback_url: Optional[HttpUrl] = Field(
        default=None,
        description="[DEPRECATED] 무시됨. SSE(/scan/{task_id}/progress)로 결과 수신.",
        json_schema_extra={"deprecated": True},
    )


class ClassificationResponse(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None
    pipeline_result: Optional[WasteClassificationResult] = None
    reward: Optional[CharacterRewardResponse] = None
    error: Optional[str] = None


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
