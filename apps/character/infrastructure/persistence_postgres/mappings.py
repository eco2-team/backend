"""ORM Mappings.

Imperative Mapping을 사용하여 도메인 엔티티를 테이블에 매핑합니다.
도메인 엔티티는 SQLAlchemy에 의존하지 않습니다.
"""

from sqlalchemy.orm import relationship

from character.domain.entities import Character, CharacterOwnership
from character.infrastructure.persistence_postgres.registry import mapper_registry
from character.infrastructure.persistence_postgres.tables import (
    character_ownerships_table,
    characters_table,
)


def start_character_mapper() -> None:
    """Character 엔티티 매퍼 시작."""
    if hasattr(Character, "__mapper__"):
        return

    mapper_registry.map_imperatively(
        Character,
        characters_table,
        properties={
            "id": characters_table.c.id,
            "code": characters_table.c.code,
            "name": characters_table.c.name,
            "description": characters_table.c.description,
            "type_label": characters_table.c.type_label,
            "dialog": characters_table.c.dialog,
            "match_label": characters_table.c.match_label,
            "created_at": characters_table.c.created_at,
            "updated_at": characters_table.c.updated_at,
        },
    )


def start_ownership_mapper() -> None:
    """CharacterOwnership 엔티티 매퍼 시작."""
    if hasattr(CharacterOwnership, "__mapper__"):
        return

    # status 컬럼을 Enum으로 변환하는 TypeDecorator 대신
    # Repository에서 변환 처리

    mapper_registry.map_imperatively(
        CharacterOwnership,
        character_ownerships_table,
        properties={
            "id": character_ownerships_table.c.id,
            "user_id": character_ownerships_table.c.user_id,
            "character_id": character_ownerships_table.c.character_id,
            "character_code": character_ownerships_table.c.character_code,
            "source": character_ownerships_table.c.source,
            "status": character_ownerships_table.c.status,
            "acquired_at": character_ownerships_table.c.acquired_at,
            "updated_at": character_ownerships_table.c.updated_at,
            "character": relationship(
                Character,
                lazy="joined",
                uselist=False,
            ),
        },
    )


def start_mappers() -> None:
    """모든 매퍼 시작.

    앱 부팅 시 한 번만 호출됩니다.
    """
    start_character_mapper()
    start_ownership_mapper()


__all__ = ["start_mappers", "start_character_mapper", "start_ownership_mapper"]
