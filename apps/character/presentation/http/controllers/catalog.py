"""Catalog HTTP Controller."""

from typing import Annotated

from fastapi import APIRouter, Depends

from apps.character.application.catalog import GetCatalogQuery
from apps.character.presentation.http.schemas import CharacterProfile
from apps.character.setup.dependencies import get_catalog_query

router = APIRouter(prefix="/character", tags=["character"])


@router.get(
    "/catalog",
    response_model=list[CharacterProfile],
    summary="캐릭터 카탈로그 조회",
    description="수집 가능한 모든 캐릭터 목록을 반환합니다.",
)
async def get_catalog(
    query: Annotated[GetCatalogQuery, Depends(get_catalog_query)],
) -> list[CharacterProfile]:
    """캐릭터 카탈로그를 조회합니다."""
    result = await query.execute()

    return [
        CharacterProfile(
            name=item.name,
            type=item.type_label.strip() if item.type_label else "",
            dialog=item.dialog.strip() if item.dialog else "",
            match=item.match_label.strip() if item.match_label else None,
        )
        for item in result.items
    ]
