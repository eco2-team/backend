"""
Core module exports.

- Settings, get_settings: Runtime configuration (FastAPI pattern)
- SERVICE_NAME, SERVICE_VERSION: Static constants
"""

from domains.chat.core.config import Settings, get_settings
from domains.chat.core.constants import SERVICE_NAME, SERVICE_VERSION

__all__ = ["Settings", "get_settings", "SERVICE_NAME", "SERVICE_VERSION"]
