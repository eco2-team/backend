"""Enums for the My domain."""

from __future__ import annotations

from enum import Enum


class UserCharacterStatus(str, Enum):
    """사용자 캐릭터 소유 상태"""

    OWNED = "owned"  # 소유 중
    BURNED = "burned"  # 소각됨
    TRADED = "traded"  # 거래됨
