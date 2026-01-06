"""HTTP Schemas."""

from character.presentation.http.schemas.catalog import (
    CatalogItemResponse,
    CatalogResponse,
    CharacterProfile,
)
from character.presentation.http.schemas.reward import (
    ClassificationRequest,
    RewardRequest,
    RewardResponse,
)

__all__ = [
    "CatalogItemResponse",
    "CatalogResponse",
    "CharacterProfile",
    "ClassificationRequest",
    "RewardRequest",
    "RewardResponse",
]
