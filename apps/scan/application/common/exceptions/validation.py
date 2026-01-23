"""검증 관련 애플리케이션 예외."""

from scan.application.common.exceptions.base import ApplicationError


class ImageUrlRequiredError(ApplicationError):
    """이미지 URL 필수 입력 누락."""

    def __init__(self) -> None:
        super().__init__("image_url is required")
