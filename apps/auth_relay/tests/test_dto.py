"""Tests for OutboxEvent DTO."""

import pytest

from apps.auth_relay.application.common.dto.outbox_event import OutboxEvent


class TestOutboxEvent:
    """OutboxEvent DTO tests."""

    def test_create_with_raw_data_only(self) -> None:
        """Should create with raw_data only."""
        event = OutboxEvent(raw_data='{"jti": "abc123"}')
        assert event.raw_data == '{"jti": "abc123"}'
        assert event.parsed_data is None

    def test_create_with_parsed_data(self) -> None:
        """Should create with both raw and parsed data."""
        parsed = {"jti": "abc123def456", "type": "access"}
        event = OutboxEvent(raw_data='{"jti": "abc123def456"}', parsed_data=parsed)
        assert event.parsed_data == parsed

    def test_jti_property_with_parsed_data(self) -> None:
        """jti property should return truncated jti from parsed_data."""
        event = OutboxEvent(
            raw_data="{}",
            parsed_data={"jti": "abc123def456ghij"},
        )
        assert event.jti == "abc123de"  # 8 chars

    def test_jti_property_without_parsed_data(self) -> None:
        """jti property should return None without parsed_data."""
        event = OutboxEvent(raw_data='{"jti": "abc"}')
        assert event.jti is None

    def test_jti_property_without_jti_key(self) -> None:
        """jti property should return empty string if jti key missing."""
        event = OutboxEvent(raw_data="{}", parsed_data={"type": "access"})
        assert event.jti == ""

    def test_immutability(self) -> None:
        """OutboxEvent should be immutable (frozen dataclass)."""
        event = OutboxEvent(raw_data="{}")
        with pytest.raises(AttributeError):
            event.raw_data = "new"  # type: ignore

    def test_equality(self) -> None:
        """Same raw_data should be equal."""
        e1 = OutboxEvent(raw_data='{"a":1}')
        e2 = OutboxEvent(raw_data='{"a":1}')
        assert e1 == e2
