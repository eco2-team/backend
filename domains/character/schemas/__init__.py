"""Pydantic schemas for the Character service."""

from .character import (
    CharacterAcquireRequest,
    CharacterAcquireResponse,
    CharacterProfile,
    CharacterSummary,
    DefaultCharacterGrantRequest,
)
from .reward import (
    CharacterRewardCandidate,
    CharacterRewardFailureReason,
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardResult,
    CharacterRewardSource,
    ClassificationSummary,
)

__all__ = [
    "CharacterAcquireRequest",
    "CharacterAcquireResponse",
    "CharacterProfile",
    "CharacterSummary",
    "DefaultCharacterGrantRequest",
    "CharacterRewardSource",
    "CharacterRewardRequest",
    "CharacterRewardResponse",
    "CharacterRewardResult",
    "CharacterRewardFailureReason",
    "CharacterRewardCandidate",
    "ClassificationSummary",
]
