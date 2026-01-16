"""NodeResult DTO Unit Tests."""

from datetime import datetime

import pytest

from chat_worker.application.dto.node_result import NodeResult, NodeStatus


class TestNodeStatus:
    """NodeStatus Enum 테스트."""

    def test_status_values(self) -> None:
        """모든 상태 값 확인."""
        assert NodeStatus.SUCCESS.value == "success"
        assert NodeStatus.FAILED.value == "failed"
        assert NodeStatus.SKIPPED.value == "skipped"
        assert NodeStatus.TIMEOUT.value == "timeout"
        assert NodeStatus.CIRCUIT_OPEN.value == "circuit_open"


class TestNodeResult:
    """NodeResult DTO 테스트."""

    def test_create_with_required_fields(self) -> None:
        """필수 필드로 생성."""
        result = NodeResult(
            node_name="waste_rag",
            status=NodeStatus.SUCCESS,
        )

        assert result.node_name == "waste_rag"
        assert result.status == NodeStatus.SUCCESS
        assert result.data == {}
        assert result.error_message is None
        assert result.latency_ms == 0.0
        assert result.retry_count == 0
        assert isinstance(result.timestamp, datetime)

    def test_create_with_all_fields(self) -> None:
        """모든 필드로 생성."""
        now = datetime.now()
        result = NodeResult(
            node_name="character",
            status=NodeStatus.FAILED,
            data={"partial": "data"},
            error_message="Network error",
            latency_ms=150.5,
            retry_count=2,
            timestamp=now,
        )

        assert result.node_name == "character"
        assert result.status == NodeStatus.FAILED
        assert result.data == {"partial": "data"}
        assert result.error_message == "Network error"
        assert result.latency_ms == 150.5
        assert result.retry_count == 2
        assert result.timestamp == now

    def test_is_success_property(self) -> None:
        """is_success 프로퍼티 테스트."""
        success = NodeResult(node_name="test", status=NodeStatus.SUCCESS)
        failed = NodeResult(node_name="test", status=NodeStatus.FAILED)
        skipped = NodeResult(node_name="test", status=NodeStatus.SKIPPED)

        assert success.is_success is True
        assert failed.is_success is False
        assert skipped.is_success is False

    def test_is_failed_property(self) -> None:
        """is_failed 프로퍼티 테스트 (timeout, circuit_open 포함)."""
        failed = NodeResult(node_name="test", status=NodeStatus.FAILED)
        timeout = NodeResult(node_name="test", status=NodeStatus.TIMEOUT)
        circuit = NodeResult(node_name="test", status=NodeStatus.CIRCUIT_OPEN)
        success = NodeResult(node_name="test", status=NodeStatus.SUCCESS)
        skipped = NodeResult(node_name="test", status=NodeStatus.SKIPPED)

        assert failed.is_failed is True
        assert timeout.is_failed is True
        assert circuit.is_failed is True
        assert success.is_failed is False
        assert skipped.is_failed is False

    def test_is_skipped_property(self) -> None:
        """is_skipped 프로퍼티 테스트."""
        skipped = NodeResult(node_name="test", status=NodeStatus.SKIPPED)
        success = NodeResult(node_name="test", status=NodeStatus.SUCCESS)

        assert skipped.is_skipped is True
        assert success.is_skipped is False

    def test_success_factory(self) -> None:
        """성공 결과 팩토리 메서드."""
        result = NodeResult.success(
            node_name="waste_rag",
            data={"context": "플라스틱은 재활용..."},
            latency_ms=150,
            retry_count=1,
        )

        assert result.node_name == "waste_rag"
        assert result.status == NodeStatus.SUCCESS
        assert result.data == {"context": "플라스틱은 재활용..."}
        assert result.latency_ms == 150
        assert result.retry_count == 1
        assert result.is_success is True

    def test_failed_factory(self) -> None:
        """실패 결과 팩토리 메서드."""
        result = NodeResult.failed(
            node_name="location",
            error_message="API timeout",
            latency_ms=5000,
            retry_count=3,
        )

        assert result.node_name == "location"
        assert result.status == NodeStatus.FAILED
        assert result.error_message == "API timeout"
        assert result.latency_ms == 5000
        assert result.retry_count == 3
        assert result.is_failed is True

    def test_timeout_factory(self) -> None:
        """타임아웃 결과 팩토리 메서드."""
        result = NodeResult.timeout(
            node_name="web_search",
            latency_ms=10000,
            retry_count=2,
        )

        assert result.node_name == "web_search"
        assert result.status == NodeStatus.TIMEOUT
        assert "Timeout after 10000ms" in result.error_message
        assert result.latency_ms == 10000
        assert result.retry_count == 2
        assert result.is_failed is True

    def test_circuit_open_factory(self) -> None:
        """Circuit Breaker 열림 팩토리 메서드."""
        result = NodeResult.circuit_open(node_name="external_api")

        assert result.node_name == "external_api"
        assert result.status == NodeStatus.CIRCUIT_OPEN
        assert result.error_message == "Circuit breaker is open"
        assert result.is_failed is True

    def test_skipped_factory_with_reason(self) -> None:
        """스킵 결과 팩토리 메서드 (reason 있음)."""
        result = NodeResult.skipped(
            node_name="character",
            reason="No character intent detected",
        )

        assert result.node_name == "character"
        assert result.status == NodeStatus.SKIPPED
        assert result.error_message == "No character intent detected"
        assert result.is_skipped is True

    def test_skipped_factory_without_reason(self) -> None:
        """스킵 결과 팩토리 메서드 (reason 없음)."""
        result = NodeResult.skipped(node_name="location")

        assert result.node_name == "location"
        assert result.status == NodeStatus.SKIPPED
        assert result.error_message is None

    def test_to_dict(self) -> None:
        """딕셔너리 변환."""
        result = NodeResult.success(
            node_name="waste_rag",
            data={"answer": "플라스틱 분리배출"},
            latency_ms=100,
        )

        d = result.to_dict()

        assert d["node_name"] == "waste_rag"
        assert d["status"] == "success"
        assert d["data"] == {"answer": "플라스틱 분리배출"}
        assert d["error_message"] is None
        assert d["latency_ms"] == 100
        assert d["retry_count"] == 0
        assert "timestamp" in d

    def test_to_dict_with_error(self) -> None:
        """딕셔너리 변환 (에러 포함)."""
        result = NodeResult.failed(
            node_name="api_call",
            error_message="Connection refused",
            latency_ms=50,
        )

        d = result.to_dict()

        assert d["status"] == "failed"
        assert d["error_message"] == "Connection refused"

    def test_data_default_empty_dict(self) -> None:
        """data 기본값은 빈 딕셔너리."""
        result = NodeResult(node_name="test", status=NodeStatus.SUCCESS)

        # 기본값이 mutable이 아닌지 확인
        assert result.data == {}
        result.data["key"] = "value"

        # 새 인스턴스는 영향 받지 않음
        result2 = NodeResult(node_name="test2", status=NodeStatus.SUCCESS)
        assert result2.data == {}
