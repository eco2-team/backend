"""Pytest configuration for scan tests."""

import sys
from unittest.mock import MagicMock

import pytest

# Celery가 설치되지 않은 환경을 위한 Mock
if "celery" not in sys.modules:
    celery_mock = MagicMock()
    celery_mock.chain = MagicMock()
    sys.modules["celery"] = celery_mock


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for anyio."""
    return "asyncio"


@pytest.fixture
def mock_celery_chain():
    """Celery chain Mock fixture."""
    chain_mock = MagicMock()
    chain_mock.return_value.apply_async = MagicMock()
    sys.modules["celery"].chain = chain_mock
    return chain_mock
