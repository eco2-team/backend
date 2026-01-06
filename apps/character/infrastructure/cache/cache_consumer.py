"""MQ 이벤트 수신 Consumer for character cache synchronization.

API 서버에서 백그라운드 스레드로 실행되며,
character.cache exchange에서 이벤트를 수신하여 로컬 캐시를 업데이트합니다.

Architecture:
    - fanout exchange: 모든 API 인스턴스가 동일한 이벤트 수신
    - exclusive queue: 각 인스턴스마다 고유한 임시 큐 생성
    - daemon thread: 메인 프로세스 종료 시 자동 종료
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import TYPE_CHECKING, Any

from kombu import Connection, Exchange, Queue
from kombu.mixins import ConsumerMixin

from character.infrastructure.cache.character_cache import (
    CharacterLocalCache,
    get_character_cache,
)

if TYPE_CHECKING:
    from kombu.transport.base import Message

logger = logging.getLogger(__name__)

# Character cache fanout exchange (domains/_shared/cache와 동일)
CACHE_EXCHANGE = Exchange(
    "character.cache",
    type="fanout",
    durable=True,
)


class CacheUpdateConsumer(ConsumerMixin):
    """캐릭터 캐시 업데이트 이벤트 수신 Consumer.

    fanout exchange를 사용하므로 모든 API 인스턴스가 동일한 이벤트를 수신합니다.
    각 인스턴스는 고유한 임시 큐를 생성하여 exclusive하게 수신합니다.

    Event types:
        - full_refresh: 전체 캐시 교체 {"type": "full_refresh", "characters": [...]}
        - upsert: 단일 캐릭터 추가/수정 {"type": "upsert", "character": {...}}
        - delete: 단일 캐릭터 삭제 {"type": "delete", "character_id": "..."}
    """

    def __init__(self, connection: Connection, cache: CharacterLocalCache | None = None) -> None:
        """Consumer 초기화.

        Args:
            connection: RabbitMQ 연결
            cache: 캐릭터 캐시 (None이면 싱글톤 사용)
        """
        self.connection = connection
        self.cache = cache or get_character_cache()
        # 각 인스턴스마다 고유한 임시 큐 (exclusive, auto_delete)
        self.queue = Queue(
            name="",  # 빈 이름 → RabbitMQ가 자동 생성
            exchange=CACHE_EXCHANGE,
            exclusive=True,  # 이 연결만 사용
            auto_delete=True,  # 연결 종료 시 삭제
        )

    def get_consumers(self, Consumer: type, channel: Any) -> list:
        """Consumer 설정."""
        return [
            Consumer(
                queues=[self.queue],
                callbacks=[self.on_message],
                accept=["json"],
            )
        ]

    def on_message(self, body: dict[str, Any], message: "Message") -> None:
        """캐시 업데이트 이벤트 처리.

        Args:
            body: 이벤트 페이로드
            message: kombu 메시지
        """
        try:
            event_type = body.get("type")

            if event_type == "full_refresh":
                characters = body.get("characters", [])
                self.cache.set_all(characters)
                logger.info(
                    "cache_event_full_refresh",
                    extra={"count": len(characters)},
                )

            elif event_type == "upsert":
                character = body.get("character")
                if character:
                    self.cache.upsert(character)
                    logger.debug(
                        "cache_event_upsert",
                        extra={"character_id": character.get("id")},
                    )

            elif event_type == "delete":
                character_id = body.get("character_id")
                if character_id:
                    self.cache.delete(character_id)
                    logger.debug(
                        "cache_event_delete",
                        extra={"character_id": character_id},
                    )

            else:
                logger.warning(
                    "cache_event_unknown",
                    extra={"event_type": event_type},
                )

            message.ack()

        except Exception as e:
            logger.exception(
                "cache_event_error",
                extra={"error": str(e), "body": body},
            )
            message.reject(requeue=False)


class CacheConsumerThread(threading.Thread):
    """캐시 Consumer를 백그라운드에서 실행하는 Thread.

    API 서버 시작 시 이 스레드를 시작하여 캐시 동기화를 유지합니다.

    Usage:
        thread = CacheConsumerThread(broker_url="amqp://...")
        thread.start()
        # ...
        thread.stop()
    """

    def __init__(self, broker_url: str, cache: CharacterLocalCache | None = None) -> None:
        """Thread 초기화.

        Args:
            broker_url: RabbitMQ broker URL
            cache: 캐릭터 캐시 (None이면 싱글톤 사용)
        """
        super().__init__(daemon=True, name="CacheConsumerThread")
        self.broker_url = broker_url
        self.cache = cache or get_character_cache()
        self._stop_event = threading.Event()
        self._consumer: CacheUpdateConsumer | None = None

    def run(self) -> None:
        """Consumer 실행."""
        logger.info("cache_consumer_thread_starting", extra={"broker": self.broker_url})

        while not self._stop_event.is_set():
            try:
                with Connection(self.broker_url, heartbeat=60) as connection:
                    self._consumer = CacheUpdateConsumer(connection, self.cache)
                    logger.info("cache_consumer_connected")

                    # ConsumerMixin.run()은 내부적으로 무한 루프
                    self._consumer.run()

            except (socket.timeout, TimeoutError, OSError) as e:
                if self._stop_event.is_set():
                    break
                logger.debug("cache_consumer_timeout", extra={"error": str(e)})
                time.sleep(1)

            except Exception as e:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    "cache_consumer_error",
                    extra={"error": str(e)},
                )
                time.sleep(5)

        logger.info("cache_consumer_thread_stopped")

    def stop(self) -> None:
        """Consumer 중지."""
        self._stop_event.set()
        if self._consumer:
            self._consumer.should_stop = True


# 전역 consumer thread (싱글톤)
_consumer_thread: CacheConsumerThread | None = None
_thread_lock = threading.Lock()


def start_cache_consumer(broker_url: str) -> CacheConsumerThread | None:
    """캐시 Consumer 스레드 시작 (싱글톤).

    Args:
        broker_url: RabbitMQ broker URL

    Returns:
        실행 중인 CacheConsumerThread 또는 None (URL 없으면)
    """
    global _consumer_thread

    if not broker_url:
        logger.warning("cache_consumer_skipped: no broker_url")
        return None

    with _thread_lock:
        if _consumer_thread is None or not _consumer_thread.is_alive():
            _consumer_thread = CacheConsumerThread(broker_url)
            _consumer_thread.start()
            logger.info("cache_consumer_started")

    return _consumer_thread


def stop_cache_consumer() -> None:
    """캐시 Consumer 스레드 중지."""
    global _consumer_thread

    with _thread_lock:
        if _consumer_thread is not None:
            _consumer_thread.stop()
            _consumer_thread.join(timeout=5)
            _consumer_thread = None
            logger.info("cache_consumer_stopped")
