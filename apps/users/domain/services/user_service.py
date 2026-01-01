"""User domain service - Core business logic."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.users.domain.entities.user import User


@dataclass
class PhoneValidationResult:
    """전화번호 유효성 검사 결과."""

    is_valid: bool
    normalized: str | None = None
    error: str | None = None


class UserService:
    """사용자 관련 도메인 로직을 담당하는 서비스.

    기존 MyService에서 도메인 로직만 추출했습니다.
    """

    @staticmethod
    def validate_and_normalize_phone(value: str) -> PhoneValidationResult:
        """전화번호를 검증하고 정규화합니다.

        Args:
            value: 원본 전화번호

        Returns:
            PhoneValidationResult: 유효성 검사 결과와 정규화된 번호
        """
        digits = re.sub(r"\D+", "", value or "")

        # 국제번호 처리
        if digits.startswith("82") and len(digits) >= 11:
            digits = "0" + digits[2:]

        # 010-XXXX-XXXX 형식
        if len(digits) == 11 and digits.startswith("010"):
            normalized = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
            return PhoneValidationResult(is_valid=True, normalized=normalized)

        # 010-XXX-XXXX 형식 (구형)
        if len(digits) == 10 and digits.startswith("01"):
            normalized = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
            return PhoneValidationResult(is_valid=True, normalized=normalized)

        return PhoneValidationResult(
            is_valid=False,
            error="Invalid phone number format",
        )

    @staticmethod
    def format_phone_for_display(value: str | None) -> str | None:
        """저장된 전화번호를 표시용으로 포맷합니다."""
        if not value:
            return None

        digits = re.sub(r"\D+", "", value)
        if digits.startswith("82") and len(digits) >= 11:
            digits = "0" + digits[2:]

        if len(digits) == 11 and digits.startswith("010"):
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

        return value

    @staticmethod
    def resolve_display_name(user: User) -> str:
        """사용자 표시명을 결정합니다.

        우선순위: nickname → name → "사용자"
        """
        candidates = [user.nickname, user.name]
        for raw in candidates:
            if raw and (value := raw.strip()):
                return value
        return "사용자"

    @staticmethod
    def resolve_nickname(user: User, fallback: str) -> str:
        """사용자 닉네임을 결정합니다.

        우선순위: nickname → name → fallback
        """
        candidates = [user.nickname, user.name, fallback]
        for raw in candidates:
            if raw and (value := raw.strip()):
                return value
        return fallback
