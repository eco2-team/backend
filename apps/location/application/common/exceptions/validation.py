"""검증 관련 예외."""

from location.application.common.exceptions.base import ApplicationError


class KakaoApiUnavailableError(ApplicationError):
    """Kakao API 키가 설정되지 않음."""

    def __init__(self) -> None:
        super().__init__("Kakao API key not configured")


class ServiceUnavailableError(ApplicationError):
    """서비스를 사용할 수 없음."""

    def __init__(self) -> None:
        super().__init__("Service not available")


class InvalidStoreCategoryError(ApplicationError):
    """유효하지 않은 store_category 값."""

    def __init__(self, value: str, allowed: list[str]) -> None:
        super().__init__(f"Invalid store_category '{value}'. Allowed values: {allowed} or 'all'.")


class InvalidPickupCategoryError(ApplicationError):
    """유효하지 않은 pickup_category 값."""

    def __init__(self, value: str, allowed: list[str]) -> None:
        super().__init__(f"Invalid pickup_category '{value}'. Allowed values: {allowed} or 'all'.")
