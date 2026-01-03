"""Pytest configuration for users tests."""

import pytest


@pytest.fixture(autouse=True)
def anyio_backend():
    """Configure pytest-asyncio to use asyncio backend."""
    return "asyncio"
