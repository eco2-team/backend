"""Scan 도메인 예외."""

from scan.domain.exceptions.base import DomainError


class ResultNotFoundError(DomainError):
    """결과를 찾을 수 없음."""

    def __init__(self, job_id: str | None = None) -> None:
        message = f"Result not found for job_id: {job_id}" if job_id else "Result not found"
        super().__init__(message)


class UnsupportedModelError(DomainError):
    """지원하지 않는 모델."""

    def __init__(self, model: str, supported_models: list[str]) -> None:
        self.model = model
        self.supported_models = supported_models
        super().__init__(f"Unsupported model: '{model}'")
