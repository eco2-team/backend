"""BlacklistEvent DTO 테스트."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.auth_worker.application.common.dto.blacklist_event import BlacklistEvent


class TestBlacklistEvent:
    """BlacklistEvent DTO 테스트."""

    def test_from_dict_full(self, sample_blacklist_data: dict) -> None:
        """모든 필드가 있는 경우 변환 테스트."""
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        assert event.type == "add"
        assert event.jti == "test-jti-12345678"
        assert event.user_id == "user-123"
        assert event.reason == "logout"
        assert isinstance(event.expires_at, datetime)
        assert isinstance(event.timestamp, datetime)

    def test_from_dict_minimal(self, sample_blacklist_data_minimal: dict) -> None:
        """최소 필드만 있는 경우 변환 테스트."""
        event = BlacklistEvent.from_dict(sample_blacklist_data_minimal)

        assert event.type == "add"
        assert event.jti == "test-jti-minimal"
        assert event.user_id is None
        assert event.reason is None

    def test_from_dict_missing_required_field(self) -> None:
        """필수 필드 누락시 KeyError."""
        with pytest.raises(KeyError):
            BlacklistEvent.from_dict({"type": "add"})  # jti 누락

    def test_from_dict_invalid_datetime(self) -> None:
        """잘못된 datetime 형식시 ValueError."""
        data = {
            "type": "add",
            "jti": "test-jti",
            "expires_at": "invalid-date",
            "timestamp": "2025-01-01T00:00:00+00:00",
        }
        with pytest.raises(ValueError):
            BlacklistEvent.from_dict(data)

    def test_to_dict(self, sample_blacklist_data: dict) -> None:
        """to_dict 변환 테스트."""
        event = BlacklistEvent.from_dict(sample_blacklist_data)
        result = event.to_dict()

        assert result["type"] == "add"
        assert result["jti"] == "test-jti-12345678"
        assert result["user_id"] == "user-123"
        assert result["reason"] == "logout"
        assert "expires_at" in result
        assert "timestamp" in result

    def test_immutable(self, sample_blacklist_data: dict) -> None:
        """frozen=True 확인."""
        event = BlacklistEvent.from_dict(sample_blacklist_data)

        with pytest.raises(AttributeError):
            event.type = "remove"  # type: ignore

    def test_equality(self, sample_blacklist_data: dict) -> None:
        """동등성 테스트."""
        event1 = BlacklistEvent.from_dict(sample_blacklist_data)
        event2 = BlacklistEvent.from_dict(sample_blacklist_data)

        assert event1 == event2
