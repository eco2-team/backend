"""Pytest Configuration for chat_worker tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add apps directory to path for imports
apps_dir = Path(__file__).parent.parent.parent
if str(apps_dir) not in sys.path:
    sys.path.insert(0, str(apps_dir))


@pytest.fixture
def anyio_backend():
    """Use asyncio for async tests."""
    return "asyncio"
