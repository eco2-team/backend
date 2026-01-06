"""Reward HTTP Schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from character.domain.enums import CharacterRewardSource


class ClassificationRequest(BaseModel):
    """분류 결과 요청."""

    major_category: str = Field(..., description="대분류")
    middle_category: str = Field(..., description="중분류")
    minor_category: str | None = Field(None, description="소분류")
    confidence: float | None = Field(None, description="신뢰도")


class RewardRequest(BaseModel):
    """리워드 평가 요청."""

    user_id: UUID = Field(..., description="사용자 ID")
    source: CharacterRewardSource = Field(..., description="리워드 소스")
    classification: ClassificationRequest = Field(..., description="분류 결과")
    # 리워드 조건 (레거시 정합성)
    disposal_rules_present: bool = Field(True, description="분리수거 규칙 존재 여부")
    insufficiencies_present: bool = Field(False, description="부적절 항목 존재 여부")


class RewardResponse(BaseModel):
    """리워드 평가 응답."""

    received: bool = Field(..., description="리워드 수신 여부")
    already_owned: bool = Field(..., description="이미 소유 여부")
    name: str | None = Field(None, description="캐릭터 이름")
    dialog: str | None = Field(None, description="캐릭터 대사")
    match_reason: str | None = Field(None, description="매칭 이유")
    character_type: str | None = Field(None, description="캐릭터 타입")
    # Deprecated: legacy compatibility
    type: str | None = Field(None, description="캐릭터 타입 (deprecated)")

    model_config = {"populate_by_name": True}
