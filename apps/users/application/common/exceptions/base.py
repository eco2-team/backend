"""Base application exceptions."""

from __future__ import annotations


class ApplicationError(Exception):
    """애플리케이션 계층 기본 예외."""

    def __init__(self, message: str = "Application error occurred") -> None:
        self.message = message
        super().__init__(message)
