"""Taskiq Broker Configuration.

RabbitMQ Topology Operator가 Exchange/Queue를 미리 생성하므로
declare_exchange=False로 설정하여 기존 리소스를 재사용합니다.

운영 환경에서는 K8s Topology 매니페스트가 다음을 생성:
- Exchange: chat_tasks (direct)
- Queue: chat.process (DLX, TTL 설정 포함)
- Binding: chat_tasks → chat.process
"""

from __future__ import annotations

import logging

from taskiq_aio_pika import AioPikaBroker

from chat_worker.setup.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# 운영 환경: Topology Operator가 미리 생성한 Exchange/Queue 사용
# 로컬 환경: declare_exchange=True로 자동 생성 (fallback)
_is_production = settings.environment in ("production", "staging", "dev")

broker = AioPikaBroker(
    url=settings.rabbitmq_url,
    declare_exchange=not _is_production,  # 운영 환경에서는 기존 사용
    exchange_name="chat_tasks",
    queue_name=settings.rabbitmq_queue,   # chat.process
)


async def startup():
    """브로커 시작."""
    await broker.startup()
    logger.info("Taskiq broker started")


async def shutdown():
    """브로커 종료."""
    await broker.shutdown()
    logger.info("Taskiq broker stopped")
