"""Email Value Object."""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.auth.domain.exceptions.validation import InvalidEmailError
from apps.auth.domain.value_objects.base import ValueObject

# RFC 5322 간소화 버전
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


@dataclass(frozen=True, slots=True)
class Email(ValueObject):
    """이메일 Value Object.

    자기 검증을 수행하여 항상 유효한 이메일만 존재합니다.
    """

    value: str

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if not self.value:
            raise InvalidEmailError("Email cannot be empty")
        if len(self.value) > 320:
            raise InvalidEmailError("Email too long (max 320 characters)")
        if not EMAIL_PATTERN.match(self.value):
            raise InvalidEmailError(f"Invalid email format: {self.value}")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        # 이메일 일부 마스킹
        local, domain = self.value.split("@")
        masked = f"{local[:2]}***@{domain}"
        return f"Email({masked})"

    @property
    def domain(self) -> str:
        """이메일 도메인 반환."""
        return self.value.split("@")[1]
