"""Taskiq Job Submitter - JobSubmitterPort 구현체.

RabbitMQ를 통해 chat_worker에 작업 제출.
"""

from __future__ import annotations

import logging

from taskiq_aio_pika import AioPikaBroker

from chat.application.chat.ports.job_submitter import JobSubmitterPort
from chat.setup.config import get_settings

logger = logging.getLogger(__name__)


class TaskiqJobSubmitter(JobSubmitterPort):
    """Taskiq 기반 작업 제출기.

    책임:
    - RabbitMQ에 task enqueue만 담당
    - 이벤트 발행 X (Worker의 책임)
    """

    def __init__(self):
        self._settings = get_settings()
        self._broker: AioPikaBroker | None = None

    async def _get_broker(self) -> AioPikaBroker:
        """브로커 lazy 초기화."""
        if self._broker is None:
            self._broker = AioPikaBroker(
                url=self._settings.rabbitmq_url,
                declare_exchange=True,
                exchange_name="chat_tasks",
            )
            await self._broker.startup()
            logger.info("TaskiqJobSubmitter broker started")
        return self._broker

    async def submit(
        self,
        job_id: str,
        session_id: str,
        user_id: str,
        message: str,
        image_url: str | None = None,
        user_location: dict[str, float] | None = None,
        model: str | None = None,
    ) -> bool:
        """작업을 큐에 제출."""
        broker = await self._get_broker()

        try:
            await broker.kick(
                task_name="chat.process",
                args=[],
                kwargs={
                    "job_id": job_id,
                    "session_id": session_id,
                    "message": message,
                    "user_id": user_id,
                    "image_url": image_url,
                    "user_location": user_location,
                    "model": model,
                },
            )

            logger.info(
                "Job submitted",
                extra={
                    "job_id": job_id,
                    "session_id": session_id,
                    "user_id": user_id,
                },
            )
            return True

        except Exception as e:
            logger.error(
                "Job submission failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            return False

    async def close(self):
        """브로커 종료."""
        if self._broker:
            await self._broker.shutdown()
            self._broker = None
