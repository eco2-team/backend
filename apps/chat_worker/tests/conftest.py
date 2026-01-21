"""Pytest Configuration for chat_worker tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add apps directory to path for imports
apps_dir = Path(__file__).parent.parent.parent
if str(apps_dir) not in sys.path:
    sys.path.insert(0, str(apps_dir))


@pytest.fixture
def anyio_backend():
    """Use asyncio for async tests."""
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_node_executor():
    """각 테스트 전에 NodeExecutor 싱글톤 리셋.

    Circuit Breaker 상태가 테스트 간에 공유되지 않도록 합니다.
    """
    from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
        NodeExecutor,
    )

    # 테스트 전 리셋
    NodeExecutor.reset_instance()

    yield

    # 테스트 후 리셋
    NodeExecutor.reset_instance()


@pytest.fixture(autouse=True)
def mock_circuit_breaker():
    """Circuit Breaker를 항상 허용 상태로 mock.

    테스트에서 Circuit Breaker가 요청을 차단하지 않도록 합니다.
    """
    from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
        NodeExecutor,
    )
    from chat_worker.infrastructure.resilience.circuit_breaker import CircuitState

    # Mock Circuit Breaker Registry
    mock_cb_registry = MagicMock()
    mock_cb = MagicMock()
    mock_cb.allow_request = AsyncMock(return_value=True)  # 항상 허용
    mock_cb.state = CircuitState.CLOSED
    mock_cb.record_success = MagicMock()
    mock_cb.record_failure = MagicMock()
    mock_cb_registry.get = MagicMock(return_value=mock_cb)

    # NodeExecutor에 mock 주입
    NodeExecutor.get_instance(cb_registry=mock_cb_registry)

    yield mock_cb_registry
