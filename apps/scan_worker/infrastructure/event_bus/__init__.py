"""Event Bus Infrastructure - Redis Streams 이벤트 발행.

Event Router + SSE Gateway 아키텍처:
- scan_worker → Redis Streams (XADD)
- Event Router → Streams 소비 → Pub/Sub 발행
- SSE Gateway → Pub/Sub 구독 → 클라이언트 전달

chat_worker와 동일한 패턴 적용.
"""

from .redis_publisher import RedisEventPublisher

__all__ = ["RedisEventPublisher"]
