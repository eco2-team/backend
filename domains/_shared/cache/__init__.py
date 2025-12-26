"""Shared cache infrastructure for event-driven local caching."""

from domains._shared.cache.character_cache import (
    CachedCharacter,
    CharacterLocalCache,
    get_character_cache,
)
from domains._shared.cache.cache_consumer import (
    CacheConsumerThread,
    CacheUpdateConsumer,
    start_cache_consumer,
    stop_cache_consumer,
)
from domains._shared.cache.cache_publisher import (
    CharacterCachePublisher,
    get_cache_publisher,
)

__all__ = [
    # Cache
    "CachedCharacter",
    "CharacterLocalCache",
    "get_character_cache",
    # Consumer
    "CacheConsumerThread",
    "CacheUpdateConsumer",
    "start_cache_consumer",
    "stop_cache_consumer",
    # Publisher
    "CharacterCachePublisher",
    "get_cache_publisher",
]
