"""Character Event DTO.

캐릭터 저장 이벤트를 나타내는 데이터 전송 객체입니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class CharacterEvent:
    """캐릭터 저장 이벤트.

    scan 도메인에서 발생한 캐릭터 획득 이벤트를 나타냅니다.
    """

    user_id: UUID
    character_id: UUID
    character_code: str
    character_name: str
    character_type: str | None = None
    character_dialog: str | None = None
    source: str = "scan"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterEvent:
        """딕셔너리에서 CharacterEvent 생성.

        Args:
            data: 이벤트 데이터

        Returns:
            CharacterEvent 인스턴스

        Raises:
            ValueError: 필수 필드가 없는 경우
        """
        try:
            return cls(
                user_id=(
                    UUID(data["user_id"]) if isinstance(data["user_id"], str) else data["user_id"]
                ),
                character_id=(
                    UUID(data["character_id"])
                    if isinstance(data["character_id"], str)
                    else data["character_id"]
                ),
                character_code=data.get("character_code", ""),
                character_name=data.get("character_name", ""),
                character_type=data.get("character_type"),
                character_dialog=data.get("character_dialog"),
                source=data.get("source", "scan"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field: {e}") from e
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid field value: {e}") from e

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "user_id": self.user_id,
            "character_id": self.character_id,
            "character_code": self.character_code,
            "character_name": self.character_name,
            "character_type": self.character_type,
            "character_dialog": self.character_dialog,
            "source": self.source,
        }
