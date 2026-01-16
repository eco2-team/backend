"""Info Service Setup."""

from info.setup.config import get_settings
from info.setup.dependencies import get_fetch_news_command

__all__ = [
    "get_settings",
    "get_fetch_news_command",
]
