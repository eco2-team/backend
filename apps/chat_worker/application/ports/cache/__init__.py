"""Cache Port - 캐싱 추상화.

Application Layer는 이 Port만 알고,
실제 구현(Redis, Memcached 등)은 Infrastructure에서 제공.
"""

from chat_worker.application.ports.cache.cache_port import CachePort

__all__ = ["CachePort"]
