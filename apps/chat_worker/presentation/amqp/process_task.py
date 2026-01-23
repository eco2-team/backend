"""Chat Process Task.

AMQP/Taskiq Task - Presentation Layer 진입점.
RabbitMQ 큐(chat.process)에서 메시지를 수신하고
Application Layer의 Command를 호출합니다.

프로토콜: AMQP (RabbitMQ)
패턴: Worker Queue (Competing Consumers)
"""

from __future__ import annotations

import logging
from typing import Any

from chat_worker.application.commands import ProcessChatRequest
from chat_worker.setup.broker import broker
from chat_worker.setup.dependencies import get_process_chat_command

logger = logging.getLogger(__name__)


@broker.task(
    task_name="chat.process",
    timeout=180,
    retry_on_error=True,
    max_retries=2,
)
async def process_chat(
    job_id: str,
    session_id: str,
    message: str,
    user_id: str | None = None,
    image_url: str | None = None,
    user_location: dict[str, float] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Chat 파이프라인 실행 Task.

    Presentation Layer의 역할:
    - 외부 입력 수신 (Taskiq Queue)
    - Use Case 호출
    - 결과 반환

    비즈니스 로직은 Use Case에서 처리.
    """
    logger.info(
        "Chat task received",
        extra={
            "job_id": job_id,
            "session_id": session_id,
            "user_id": user_id,
        },
    )

    try:
        # Command 가져오기 (DI - CQRS)
        command = await get_process_chat_command(model=model)

        # Request DTO 생성
        request = ProcessChatRequest(
            job_id=job_id,
            session_id=session_id,
            user_id=user_id or "anonymous",
            message=message,
            image_url=image_url,
            user_location=user_location,
            model=model,
        )

        # Command 실행
        response = await command.execute(request)

        # Response 변환
        return {
            "job_id": response.job_id,
            "session_id": response.session_id,
            "status": response.status,
            "intent": response.intent,
            "answer": response.answer,
            "error": response.error,
        }

    except Exception as e:
        logger.error(
            "Chat task failed at presentation layer",
            extra={
                "job_id": job_id,
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        return {
            "job_id": job_id,
            "session_id": session_id,
            "status": "failed",
            "intent": None,
            "answer": None,
            "error": f"Internal error: {type(e).__name__}: {str(e)[:200]}",
        }


# ============================================================
# Health Check Task
# ============================================================


@broker.task(task_name="chat.health")
async def health_check() -> dict[str, str]:
    """Worker 헬스체크 Task."""
    return {"status": "healthy", "service": "chat-worker"}
