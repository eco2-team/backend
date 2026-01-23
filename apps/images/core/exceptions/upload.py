"""업로드 관련 예외."""


class UploaderMismatchError(Exception):
    """업로더 불일치."""

    def __init__(self) -> None:
        self.message = "Uploader mismatch"
        super().__init__(self.message)
