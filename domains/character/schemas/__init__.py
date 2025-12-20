"""Pydantic schemas for the Character service."""

from .catalog import (
    CharacterAcquireResponse,
    CharacterProfile,
    DefaultCharacterGrantRequest,
    GrantCharacterRequest,
)
from .reward import (
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)

__all__ = [
    "CharacterAcquireResponse",
    "CharacterProfile",
    "DefaultCharacterGrantRequest",
    "GrantCharacterRequest",
    "CharacterRewardSource",
    "CharacterRewardRequest",
    "CharacterRewardResponse",
    "CharacterRewardFailureReason",
    "ClassificationSummary",
]
