"""Characters controller - User character endpoints."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from apps.users.application.queries import CheckCharacterOwnershipQuery, GetCharactersQuery
from apps.users.presentation.http.schemas import (
    CharacterListResponse,
    CharacterOwnershipResponse,
    UserCharacterResponse,
)
from apps.users.setup.dependencies import (
    get_check_character_ownership_query,
    get_get_characters_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/me/characters", tags=["characters"])


def get_auth_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> UUID:
    """ext-authz에서 전달된 사용자 ID를 추출합니다."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user ID",
        )
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format",
        )


@router.get("", response_model=CharacterListResponse)
async def get_characters(
    auth_user_id: UUID = Depends(get_auth_user_id),
    query: GetCharactersQuery = Depends(get_get_characters_query),
) -> CharacterListResponse:
    """현재 사용자의 캐릭터 목록을 조회합니다."""
    characters = await query.execute(auth_user_id)
    return CharacterListResponse(
        characters=[
            UserCharacterResponse(
                id=c.id,
                character_id=c.character_id,
                character_code=c.character_code,
                character_name=c.character_name,
                character_type=c.character_type,
                character_dialog=c.character_dialog,
                source=c.source,
                status=c.status,
                acquired_at=c.acquired_at,
            )
            for c in characters
        ],
        total=len(characters),
    )


@router.get("/{character_code}/ownership", response_model=CharacterOwnershipResponse)
async def check_character_ownership(
    character_code: str,
    auth_user_id: UUID = Depends(get_auth_user_id),
    query: CheckCharacterOwnershipQuery = Depends(get_check_character_ownership_query),
) -> CharacterOwnershipResponse:
    """특정 캐릭터의 소유 여부를 확인합니다."""
    ownership = await query.execute(auth_user_id, character_code)
    return CharacterOwnershipResponse(
        character_code=ownership.character_code,
        owned=ownership.owned,
        acquired_at=ownership.acquired_at,
    )
