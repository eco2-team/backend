"""Tests for RelayResult."""

import pytest

from apps.auth_relay.application.common.result import RelayResult, ResultStatus


class TestResultStatus:
    """ResultStatus enum tests."""

    def test_enum_values(self) -> None:
        """Should have correct enum values."""
        assert ResultStatus.SUCCESS is not None
        assert ResultStatus.RETRYABLE is not None
        assert ResultStatus.DROP is not None

    def test_enum_uniqueness(self) -> None:
        """Each status should be unique."""
        statuses = [ResultStatus.SUCCESS, ResultStatus.RETRYABLE, ResultStatus.DROP]
        assert len(set(statuses)) == 3


class TestRelayResult:
    """RelayResult tests."""

    def test_success_factory(self) -> None:
        """success() should create SUCCESS result."""
        result = RelayResult.success()
        assert result.status == ResultStatus.SUCCESS
        assert result.is_success is True
        assert result.is_retryable is False
        assert result.should_drop is False

    def test_success_with_message(self) -> None:
        """success() should accept optional message."""
        result = RelayResult.success("Event relayed")
        assert result.message == "Event relayed"

    def test_retryable_factory(self) -> None:
        """retryable() should create RETRYABLE result."""
        result = RelayResult.retryable("Connection timeout")
        assert result.status == ResultStatus.RETRYABLE
        assert result.is_success is False
        assert result.is_retryable is True
        assert result.should_drop is False
        assert result.message == "Connection timeout"

    def test_drop_factory(self) -> None:
        """drop() should create DROP result."""
        result = RelayResult.drop("Invalid format")
        assert result.status == ResultStatus.DROP
        assert result.is_success is False
        assert result.is_retryable is False
        assert result.should_drop is True
        assert result.message == "Invalid format"

    def test_immutability(self) -> None:
        """RelayResult should be immutable (frozen dataclass)."""
        result = RelayResult.success()
        with pytest.raises(AttributeError):
            result.status = ResultStatus.DROP  # type: ignore

    def test_equality(self) -> None:
        """Same status and message should be equal."""
        r1 = RelayResult.success("msg")
        r2 = RelayResult.success("msg")
        assert r1 == r2

    def test_inequality(self) -> None:
        """Different results should not be equal."""
        r1 = RelayResult.success()
        r2 = RelayResult.retryable("error")
        assert r1 != r2
