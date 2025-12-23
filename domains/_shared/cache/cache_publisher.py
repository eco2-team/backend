"""MQ 이벤트 발행 Publisher for character cache synchronization.

Character API에서 CRUD 작업 후 호출하여
모든 Worker의 로컬 캐시를 동기화합니다.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from kombu import Connection, Exchange, Producer

logger = logging.getLogger(__name__)

# Character cache fanout exchange (cache_consumer.py와 동일)
CACHE_EXCHANGE = Exchange(
    "character.cache",
    type="fanout",
    durable=True,
)


class CharacterCachePublisher:
    """캐릭터 캐시 이벤트 발행자.

    Character API에서 CRUD 작업 후 호출하여
    character.cache exchange로 이벤트를 발행합니다.

    Usage:
        publisher = CharacterCachePublisher(broker_url="amqp://...")
        publisher.publish_upsert({"id": "...", "name": "...", ...})
    """

    def __init__(self, broker_url: str):
        """Publisher 초기화.

        Args:
            broker_url: RabbitMQ broker URL
        """
        self.broker_url = broker_url

    def publish_upsert(self, character: dict[str, Any]) -> None:
        """캐릭터 추가/수정 이벤트 브로드캐스트.

        Args:
            character: 캐릭터 데이터 dict
        """
        self._publish(
            {
                "type": "upsert",
                "character": character,
            }
        )
        logger.info(
            "cache_publish_upsert",
            extra={"character_id": character.get("id")},
        )

    def publish_delete(self, character_id: str | UUID) -> None:
        """캐릭터 삭제 이벤트 브로드캐스트.

        Args:
            character_id: 삭제된 캐릭터 ID
        """
        self._publish(
            {
                "type": "delete",
                "character_id": str(character_id),
            }
        )
        logger.info(
            "cache_publish_delete",
            extra={"character_id": str(character_id)},
        )

    def publish_full_refresh(self, characters: list[dict[str, Any]]) -> None:
        """전체 캐시 갱신 이벤트 브로드캐스트.

        모든 Worker의 캐시를 전체 교체합니다.
        주로 관리자 도구나 스케줄러에서 사용합니다.

        Args:
            characters: 전체 캐릭터 목록
        """
        self._publish(
            {
                "type": "full_refresh",
                "characters": characters,
            }
        )
        logger.info(
            "cache_publish_full_refresh",
            extra={"count": len(characters)},
        )

    def _publish(self, body: dict[str, Any]) -> None:
        """이벤트 발행.

        Args:
            body: 이벤트 페이로드
        """
        try:
            with Connection(self.broker_url) as conn:
                producer = Producer(conn)
                producer.publish(
                    body,
                    exchange=CACHE_EXCHANGE,
                    serializer="json",
                    declare=[CACHE_EXCHANGE],
                )
        except Exception as e:
            logger.exception(
                "cache_publish_error",
                extra={"error": str(e), "body": body},
            )
            raise


# 싱글톤 publisher 인스턴스
_publisher: CharacterCachePublisher | None = None


def get_cache_publisher(broker_url: str | None = None) -> CharacterCachePublisher:
    """싱글톤 Publisher 인스턴스 반환.

    Args:
        broker_url: RabbitMQ broker URL (최초 호출 시 필수)

    Returns:
        CharacterCachePublisher 인스턴스

    Raises:
        ValueError: broker_url 없이 최초 호출 시
    """
    global _publisher

    if _publisher is None:
        if broker_url is None:
            import os

            broker_url = os.getenv("CELERY_BROKER_URL")
            if not broker_url:
                raise ValueError("broker_url is required for first call")
        _publisher = CharacterCachePublisher(broker_url)

    return _publisher
