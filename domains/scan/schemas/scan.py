from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl

from domains._shared.schemas.waste import WasteClassificationResult
from domains.character.schemas.reward import CharacterRewardResponse


class ClassificationRequest(BaseModel):
    image_url: Optional[HttpUrl] = Field(default=None, description="단일 이미지 URL (하위호환)")
    image_urls: Optional[List[HttpUrl]] = Field(default=None, description="다중 이미지 URL 목록")
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
