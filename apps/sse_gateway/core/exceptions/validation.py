"""검증 관련 예외."""


class InvalidJobIdError(Exception):
    """유효하지 않은 job_id."""

    def __init__(self) -> None:
        self.message = "유효하지 않은 job_id입니다"
        super().__init__(self.message)


class UnsupportedServiceError(Exception):
    """지원하지 않는 서비스."""

    def __init__(self, supported: set[str]) -> None:
        self.supported = supported
        self.message = f"지원하지 않는 서비스입니다. (지원: {', '.join(sorted(supported))})"
        super().__init__(self.message)
