"""CommandResult 테스트."""

from __future__ import annotations

import pytest

from apps.auth_worker.application.common.result import CommandResult, ResultStatus


class TestResultStatus:
    """ResultStatus enum 테스트."""

    def test_enum_values(self) -> None:
        """enum 값 존재 확인."""
        assert ResultStatus.SUCCESS is not None
        assert ResultStatus.RETRYABLE is not None
        assert ResultStatus.DROP is not None

    def test_enum_unique(self) -> None:
        """enum 값 고유성 확인."""
        values = [s.value for s in ResultStatus]
        assert len(values) == len(set(values))


class TestCommandResult:
    """CommandResult 테스트."""

    def test_success_factory(self) -> None:
        """success() 팩토리 메서드."""
        result = CommandResult.success()

        assert result.status == ResultStatus.SUCCESS
        assert result.is_success is True
        assert result.is_retryable is False
        assert result.should_drop is False
        assert result.message is None

    def test_success_with_message(self) -> None:
        """메시지가 있는 success."""
        result = CommandResult.success("Operation completed")

        assert result.is_success is True
        assert result.message == "Operation completed"

    def test_retryable_factory(self) -> None:
        """retryable() 팩토리 메서드."""
        result = CommandResult.retryable("Connection timeout")

        assert result.status == ResultStatus.RETRYABLE
        assert result.is_success is False
        assert result.is_retryable is True
        assert result.should_drop is False
        assert result.message == "Connection timeout"

    def test_drop_factory(self) -> None:
        """drop() 팩토리 메서드."""
        result = CommandResult.drop("Invalid format")

        assert result.status == ResultStatus.DROP
        assert result.is_success is False
        assert result.is_retryable is False
        assert result.should_drop is True
        assert result.message == "Invalid format"

    def test_immutable(self) -> None:
        """frozen=True 확인."""
        result = CommandResult.success()

        with pytest.raises(AttributeError):
            result.status = ResultStatus.DROP  # type: ignore

    def test_equality(self) -> None:
        """동등성 테스트."""
        result1 = CommandResult.success("msg")
        result2 = CommandResult.success("msg")

        assert result1 == result2

    def test_inequality(self) -> None:
        """비동등성 테스트."""
        result1 = CommandResult.success()
        result2 = CommandResult.retryable("error")

        assert result1 != result2
