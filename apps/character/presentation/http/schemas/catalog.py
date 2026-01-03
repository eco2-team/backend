"""Catalog HTTP Schemas."""

from pydantic import BaseModel, Field


class CharacterProfile(BaseModel):
    """캐릭터 프로필.

    domains/character/schemas/catalog.py의 CharacterProfile과 동일합니다.
    """

    name: str = Field(..., description="캐릭터 이름")
    type: str = Field(..., description="캐릭터 타입")
    dialog: str = Field(..., description="캐릭터 대사")
    match: str | None = Field(None, description="매칭 라벨")


class CatalogItemResponse(BaseModel):
    """카탈로그 아이템 응답 (확장 버전)."""

    code: str = Field(..., description="캐릭터 코드")
    name: str = Field(..., description="캐릭터 이름")
    type_label: str = Field(..., description="캐릭터 타입", alias="type")
    description: str | None = Field(None, description="캐릭터 설명")

    model_config = {"populate_by_name": True}


class CatalogResponse(BaseModel):
    """카탈로그 응답 (확장 버전)."""

    items: list[CatalogItemResponse] = Field(..., description="캐릭터 목록")
    total: int = Field(..., description="전체 개수")
