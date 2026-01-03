"""ORM to Domain Mappers."""

from apps.character.domain.entities import Character, CharacterOwnership
from apps.character.domain.enums import CharacterOwnershipStatus
from apps.character.infrastructure.persistence_postgres.models import (
    CharacterModel,
    CharacterOwnershipModel,
)


def character_model_to_entity(model: CharacterModel) -> Character:
    """CharacterModel을 Character 엔티티로 변환합니다."""
    return Character(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        type_label=model.type_label,
        dialog=model.dialog,
        match_label=model.match_label,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def ownership_model_to_entity(model: CharacterOwnershipModel) -> CharacterOwnership:
    """CharacterOwnershipModel을 CharacterOwnership 엔티티로 변환합니다."""
    character = None
    if model.character:
        character = character_model_to_entity(model.character)

    return CharacterOwnership(
        id=model.id,
        user_id=model.user_id,
        character_id=model.character_id,
        character_code=model.character_code,
        source=model.source,
        status=CharacterOwnershipStatus(model.status),
        acquired_at=model.acquired_at,
        updated_at=model.updated_at,
        character=character,
    )
