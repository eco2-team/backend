"""Blacklist Outbox Relay Worker.

Redis Outbox에서 실패한 블랙리스트 이벤트를 RabbitMQ로 재발행.

Architecture:
    auth-api (logout)
        │
        ├── 1차 시도: RabbitMQ 직접 발행 (성공률 ~99%)
        │
        └── 실패 시: Redis Outbox에 적재 (LPUSH)
                │
                └── Relay Worker (이 모듈)
                        │
                        └── RPOP → RabbitMQ 재발행

Redis Keys:
    - outbox:blacklist        # List: 실패한 이벤트 (FIFO)
    - outbox:blacklist:dlq    # List: 재발행도 실패한 이벤트 (수동 처리)

Run:
    python -m domains.auth.tasks.blacklist_relay
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from typing import Optional

import pika
import pika.exceptions
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("AUTH_REDIS_URL", "redis://localhost:6379/0")
AMQP_URL = os.getenv("AUTH_AMQP_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE_NAME = "blacklist.events"
OUTBOX_KEY = "outbox:blacklist"
DLQ_KEY = "outbox:blacklist:dlq"
POLL_INTERVAL = float(os.getenv("RELAY_POLL_INTERVAL", "1.0"))  # seconds
BATCH_SIZE = int(os.getenv("RELAY_BATCH_SIZE", "10"))


class BlacklistRelay:
    """Redis Outbox → RabbitMQ Relay Worker."""

    def __init__(self) -> None:
        self._redis: Optional[Redis] = None
        self._mq_connection: Optional[pika.BlockingConnection] = None
        self._mq_channel: Optional[pika.channel.Channel] = None
        self._shutdown = False
        self._processed_total = 0
        self._failed_total = 0

    async def start(self) -> None:
        """Start the relay worker."""
        logger.info("Blacklist Relay starting...")

        # Connect to Redis
        self._redis = Redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await self._redis.ping()
            logger.info("Redis connected", extra={"url": REDIS_URL[:30] + "..."})
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise

        # Connect to RabbitMQ
        self._connect_mq()

        # Setup graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Log initial queue depth
        depth = await self._redis.llen(OUTBOX_KEY)
        logger.info(
            "Starting relay loop",
            extra={
                "poll_interval": POLL_INTERVAL,
                "batch_size": BATCH_SIZE,
                "initial_queue_depth": depth,
            },
        )

        # Main loop
        await self._run()

    def _connect_mq(self) -> None:
        """Connect to RabbitMQ."""
        try:
            params = pika.URLParameters(AMQP_URL)
            self._mq_connection = pika.BlockingConnection(params)
            self._mq_channel = self._mq_connection.channel()

            # Declare fanout exchange (idempotent)
            self._mq_channel.exchange_declare(
                exchange=EXCHANGE_NAME,
                exchange_type="fanout",
                durable=True,
            )
            logger.info("RabbitMQ connected", extra={"exchange": EXCHANGE_NAME})
        except Exception as e:
            logger.error(f"RabbitMQ connection failed: {e}")
            raise

    def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown = True

    async def _run(self) -> None:
        """Main polling loop."""
        while not self._shutdown:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    await asyncio.sleep(POLL_INTERVAL)
            except pika.exceptions.AMQPConnectionError:
                logger.warning("MQ connection lost, reconnecting...")
                await asyncio.sleep(POLL_INTERVAL * 2)
                self._reconnect_mq()
            except Exception:
                logger.exception("Relay loop error")
                await asyncio.sleep(POLL_INTERVAL * 2)

        await self._cleanup()

    async def _process_batch(self) -> int:
        """Process a batch from the outbox."""
        processed = 0

        for _ in range(BATCH_SIZE):
            # RPOP: FIFO order (events are LPUSH'd)
            event_json = await self._redis.rpop(OUTBOX_KEY)
            if not event_json:
                break

            try:
                event = json.loads(event_json)
                self._publish_to_mq(event)
                processed += 1
                self._processed_total += 1
                logger.debug(
                    "Event relayed",
                    extra={"jti": event.get("jti", "")[:8]},
                )
            except pika.exceptions.AMQPError as e:
                # MQ failure → re-queue (push back to front)
                await self._redis.lpush(OUTBOX_KEY, event_json)
                logger.warning(f"MQ publish failed, re-queued: {e}")
                self._reconnect_mq()
                break
            except json.JSONDecodeError:
                # Invalid JSON → DLQ
                await self._redis.lpush(DLQ_KEY, event_json)
                self._failed_total += 1
                logger.error("Invalid JSON, moved to DLQ")
            except Exception as e:
                # Other errors → DLQ
                await self._redis.lpush(DLQ_KEY, event_json)
                self._failed_total += 1
                logger.exception(f"Unexpected error, moved to DLQ: {e}")

        if processed > 0:
            logger.info(
                "Batch processed",
                extra={
                    "processed": processed,
                    "total_processed": self._processed_total,
                    "total_failed": self._failed_total,
                },
            )

        return processed

    def _publish_to_mq(self, event: dict) -> None:
        """Publish event to RabbitMQ."""
        body = json.dumps(event, ensure_ascii=False)
        self._mq_channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="",
            body=body.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json",
            ),
        )

    def _reconnect_mq(self) -> None:
        """Reconnect to RabbitMQ."""
        try:
            if self._mq_connection and not self._mq_connection.is_closed:
                self._mq_connection.close()
        except Exception:
            pass

        try:
            self._connect_mq()
        except Exception as e:
            logger.error(f"MQ reconnect failed: {e}")

    async def _cleanup(self) -> None:
        """Cleanup resources."""
        logger.info(
            "Shutting down",
            extra={
                "total_processed": self._processed_total,
                "total_failed": self._failed_total,
            },
        )

        if self._redis:
            await self._redis.close()

        if self._mq_connection and not self._mq_connection.is_closed:
            self._mq_connection.close()

        logger.info("Relay shutdown complete")


async def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    relay = BlacklistRelay()
    await relay.start()


if __name__ == "__main__":
    asyncio.run(main())
