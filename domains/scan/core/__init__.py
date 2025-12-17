"""
Core module exports.

- Settings, get_settings: Runtime configuration (FastAPI pattern)
- SERVICE_NAME, SERVICE_VERSION: Static constants
"""

from .config import Settings, get_settings
from .constants import SERVICE_NAME, SERVICE_VERSION

__all__ = ["Settings", "get_settings", "SERVICE_NAME", "SERVICE_VERSION"]
