"""Eval Pipeline DI Wiring Integration Tests.

Phase 3+4 통합 테스트: DI wiring, eval subgraph + counter, PG pool, recalibrate stub.
모든 외부 의존성은 mock 처리.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_worker.application.dto.eval_config import EvalConfig
from chat_worker.application.services.eval.calibration_monitor import (
    CalibrationMonitorService,
    STATUS_RECALIBRATING,
)
from chat_worker.infrastructure.orchestration.langgraph.eval_graph_factory import (
    create_eval_subgraph,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.eval_node import (
    create_eval_entry_node,
)
from chat_worker.infrastructure.persistence.eval.composite_eval_gateway import (
    CompositeEvalCommandGateway,
    CompositeEvalQueryGateway,
)
from chat_worker.infrastructure.persistence.eval.json_calibration_adapter import (
    JsonCalibrationDataAdapter,
)
from chat_worker.infrastructure.persistence.eval.postgres_eval_result_adapter import (
    PostgresEvalResultAdapter,
)
from chat_worker.infrastructure.persistence.eval.redis_eval_counter import (
    RedisEvalCounter,
)
from chat_worker.infrastructure.persistence.eval.redis_eval_result_adapter import (
    RedisEvalResultAdapter,
)


@pytest.mark.eval_unit
class TestEvalCounterWiring:
    """eval_counter가 eval_entry_node에 주입되었을 때 동작 검증."""

    async def test_eval_entry_uses_counter_when_injected(self) -> None:
        """eval_counter 주입 시 increment_and_check() 호출."""
        counter = AsyncMock(spec=RedisEvalCounter)
        counter.increment_and_check.return_value = (100, True)

        node = create_eval_entry_node(
            eval_config=EvalConfig(eval_cusum_check_interval=100),
            eval_counter=counter,
        )

        state = {
            "message": "테스트",
            "intent": "waste",
            "answer": "답변",
            "eval_retry_count": 0,
        }
        result = await node(state)

        counter.increment_and_check.assert_called_once()
        assert result["should_run_calibration"] is True

    async def test_eval_entry_counter_not_triggered(self) -> None:
        """interval 비배수에서 should_run_calibration=False."""
        counter = AsyncMock(spec=RedisEvalCounter)
        counter.increment_and_check.return_value = (99, False)

        node = create_eval_entry_node(
            eval_config=EvalConfig(),
            eval_counter=counter,
        )

        state = {"message": "테스트", "intent": "waste", "answer": "답변"}
        result = await node(state)

        assert result["should_run_calibration"] is False

    async def test_eval_entry_counter_failure_falls_back(self) -> None:
        """eval_counter 실패 시 stopgap fallback."""
        counter = AsyncMock(spec=RedisEvalCounter)
        counter.increment_and_check.side_effect = Exception("Redis down")

        node = create_eval_entry_node(
            eval_config=EvalConfig(eval_cusum_check_interval=100),
            eval_counter=counter,
        )

        state = {"message": "테스트", "intent": "waste", "answer": "답변"}
        result = await node(state)

        # fallback: retry_count=0이므로 False
        assert result["should_run_calibration"] is False

    async def test_eval_entry_no_counter_uses_stopgap(self) -> None:
        """eval_counter=None일 때 stopgap 사용."""
        node = create_eval_entry_node(
            eval_config=EvalConfig(eval_cusum_check_interval=1),
            eval_counter=None,
        )

        state = {
            "message": "테스트",
            "intent": "waste",
            "answer": "답변",
            "eval_retry_count": 1,
        }
        result = await node(state)

        # stopgap: retry_count=1, interval=1 → True
        assert result["should_run_calibration"] is True


@pytest.mark.eval_unit
class TestEvalSubgraphWithCounter:
    """eval_counter가 create_eval_subgraph에 전달되는지 검증."""

    def test_create_eval_subgraph_accepts_counter(self) -> None:
        """eval_counter 파라미터를 수용하는지 검증."""
        counter = AsyncMock(spec=RedisEvalCounter)

        # TypeError 없이 컴파일되어야 함
        subgraph = create_eval_subgraph(
            eval_config=EvalConfig(),
            eval_counter=counter,
        )
        assert subgraph is not None

    def test_create_eval_subgraph_without_counter(self) -> None:
        """eval_counter 없이도 하위 호환 유지."""
        subgraph = create_eval_subgraph(eval_config=EvalConfig())
        assert subgraph is not None


@pytest.mark.eval_unit
class TestRecalibrateStub:
    """CalibrationMonitorService.recalibrate() stub 검증."""

    async def test_recalibrate_returns_stub(self) -> None:
        """recalibrate()가 stub 결과를 반환."""
        service = CalibrationMonitorService(
            eval_query_gw=AsyncMock(),
            calibration_gw=AsyncMock(),
            bars_evaluator=AsyncMock(),
        )

        result = await service.recalibrate()

        assert result["status"] == STATUS_RECALIBRATING
        assert result["action"] == "stub_logged"


@pytest.mark.eval_unit
class TestGatewayAssembly:
    """Gateway 어댑터 조립 검증."""

    def test_composite_command_gateway_redis_only(self) -> None:
        """Redis-only 모드로 CompositeEvalCommandGateway 생성."""
        redis_adapter = AsyncMock(spec=RedisEvalResultAdapter)
        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        assert gw is not None

    def test_composite_query_gateway_redis_only(self) -> None:
        """Redis-only 모드로 CompositeEvalQueryGateway 생성."""
        redis_adapter = AsyncMock(spec=RedisEvalResultAdapter)
        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=None,
        )
        assert gw is not None

    def test_json_calibration_adapter_creation(self) -> None:
        """JsonCalibrationDataAdapter 기본 경로로 생성."""
        adapter = JsonCalibrationDataAdapter()
        assert adapter is not None

    async def test_json_calibration_adapter_loads_fixture(self) -> None:
        """Fixture 파일에서 Calibration Set 로드."""
        adapter = JsonCalibrationDataAdapter()
        samples = await adapter.get_calibration_set()

        assert len(samples) >= 5  # 최소 5개 샘플
        version = await adapter.get_calibration_version()
        assert version.startswith("v1.0")

    def test_redis_eval_counter_creation(self) -> None:
        """RedisEvalCounter 생성."""
        redis = AsyncMock()
        counter = RedisEvalCounter(redis=redis, interval=50)
        assert counter.interval == 50


@pytest.mark.eval_unit
class TestPgPoolWiring:
    """Phase 4: PG pool DI wiring 검증."""

    def test_pg_adapter_accepts_pool(self) -> None:
        """PostgresEvalResultAdapter가 pool을 수용하는지 검증."""
        pg_pool = MagicMock()
        adapter = PostgresEvalResultAdapter(pool=pg_pool)
        assert adapter is not None
        assert adapter._pool is pg_pool

    def test_composite_command_gateway_with_pg_adapter(self) -> None:
        """PG adapter 주입 시 CompositeEvalCommandGateway 생성."""
        redis_adapter = AsyncMock(spec=RedisEvalResultAdapter)
        pg_pool = MagicMock()
        pg_adapter = PostgresEvalResultAdapter(pool=pg_pool)

        gw = CompositeEvalCommandGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        assert gw is not None

    def test_composite_query_gateway_with_pg_adapter(self) -> None:
        """PG adapter 주입 시 CompositeEvalQueryGateway 생성."""
        redis_adapter = AsyncMock(spec=RedisEvalResultAdapter)
        pg_pool = MagicMock()
        pg_adapter = PostgresEvalResultAdapter(pool=pg_pool)

        gw = CompositeEvalQueryGateway(
            redis_adapter=redis_adapter,
            pg_adapter=pg_adapter,
        )
        assert gw is not None

    def test_config_has_pg_dsn_fields(self) -> None:
        """Settings에 eval PG 관련 필드가 존재하는지 검증.

        broker 모듈 의존성으로 인해 setup 패키지 직접 import 불가.
        sys.modules mock으로 우회.
        """
        import sys

        # broker 의존성 mock (taskiq_aio_pika)
        mock_taskiq = MagicMock()
        original = sys.modules.get("taskiq_aio_pika")
        sys.modules["taskiq_aio_pika"] = mock_taskiq
        try:
            from chat_worker.setup.config import Settings

            settings = Settings()
            assert hasattr(settings, "eval_postgres_dsn")
            assert hasattr(settings, "eval_pg_pool_min_size")
            assert hasattr(settings, "eval_pg_pool_max_size")
            # 기본값 검증
            assert settings.eval_postgres_dsn == ""
            assert settings.eval_pg_pool_min_size == 2
            assert settings.eval_pg_pool_max_size == 5
        finally:
            if original is None:
                sys.modules.pop("taskiq_aio_pika", None)
            else:
                sys.modules["taskiq_aio_pika"] = original

    def test_eval_config_accepts_enabled_true(self) -> None:
        """EvalConfig에 enable_eval_pipeline=True 전달 시 동작 검증."""
        eval_config = EvalConfig(enable_eval_pipeline=True)
        assert eval_config.enable_eval_pipeline is True
