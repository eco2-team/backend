"""Reward grant task with DLQ support.

리워드 지급을 비동기로 처리하며, 실패 시 재시도 후 DLQ로 이동합니다.
Circuit Breaker 대신 MQ의 재시도 메커니즘을 사용합니다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from domains._shared.taskqueue import celery_app
from domains._shared.taskqueue.state import get_state_manager

logger = logging.getLogger(__name__)


@dataclass
class RewardRequest:
    """리워드 요청 데이터."""

    task_id: str
    user_id: str
    category: str
    amount: int = 10  # 기본 포인트
    retry_count: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@celery_app.task(
    bind=True,
    name="domains.scan.tasks.reward.reward_grant",
    max_retries=3,
    default_retry_delay=60,  # 1분 간격 재시도
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,  # 최대 5분
    retry_jitter=True,
    # DLQ 설정: 최종 실패 시 dead letter queue로 이동
    acks_late=True,
    reject_on_worker_lost=True,
)
def reward_grant(
    self,
    task_id: str,
    user_id: str,
    category: str,
    amount: int = 10,
) -> dict:
    """리워드 지급 태스크.

    gRPC를 통해 Character 서비스에 리워드를 요청합니다.
    실패 시 자동 재시도되며, 최종 실패 시 DLQ로 이동합니다.

    Args:
        task_id: 분류 태스크 ID (추적용)
        user_id: 사용자 UUID
        category: 분류 카테고리 (major_category)
        amount: 보상 포인트 (기본 10)

    Returns:
        리워드 지급 결과

    Raises:
        Exception: gRPC 호출 실패 시 (재시도 트리거)
    """
    retry_count = self.request.retries
    logger.info(
        f"[{task_id}] reward_grant attempt {retry_count + 1}/{self.max_retries + 1} "
        f"for user={user_id}, category={category}"
    )

    # 상태 업데이트
    async def update_processing():
        manager = get_state_manager()
        await manager.update(
            task_id,
            reward_status="processing" if retry_count == 0 else "retrying",
        )

    asyncio.get_event_loop().run_until_complete(update_processing())

    try:
        # gRPC 클라이언트 (Circuit Breaker 없이 직접 호출)
        # MQ가 재시도를 담당하므로 CB 불필요
        from domains.scan.core.config import get_settings
        from domains.scan.core.grpc_client import CharacterGrpcClient

        settings = get_settings()
        client = CharacterGrpcClient(settings)

        # 동기 gRPC 호출 (asyncio loop 내에서)
        async def call_grpc():
            return await client.get_character_reward(
                user_id=user_id,
                category=category,
            )

        result = asyncio.get_event_loop().run_until_complete(call_grpc())

        if result is None:
            # gRPC 실패 (CB Open 포함) - 재시도
            raise RuntimeError(f"gRPC call returned None for task {task_id}")

        logger.info(f"[{task_id}] reward_grant succeeded: {result}")

        # 성공 상태 업데이트
        async def mark_granted():
            manager = get_state_manager()
            await manager.update(
                task_id,
                reward_status="granted",
            )

        asyncio.get_event_loop().run_until_complete(mark_granted())

        return {
            "task_id": task_id,
            "user_id": user_id,
            "category": category,
            "amount": amount,
            "status": "granted",
            "reward_data": result,
        }

    except Exception as exc:
        logger.warning(f"[{task_id}] reward_grant failed (attempt {retry_count + 1}): {exc}")

        # 최종 실패인지 확인
        if retry_count >= self.max_retries:
            logger.error(
                f"[{task_id}] reward_grant permanently failed after "
                f"{self.max_retries + 1} attempts"
            )

            # DLQ 상태로 마킹
            async def mark_dlq():
                manager = get_state_manager()
                await manager.update(
                    task_id,
                    reward_status="failed",
                )

            asyncio.get_event_loop().run_until_complete(mark_dlq())

            # 알림 발송 (선택적)
            _notify_reward_failure(task_id, user_id, category, str(exc))

            # 재시도하지 않고 실패 처리
            # raise Reject(exc, requeue=False)  # DLQ로 이동
            raise

        # 재시도 대기 중 상태
        async def mark_queued():
            manager = get_state_manager()
            await manager.update(
                task_id,
                reward_status="queued",
            )

        asyncio.get_event_loop().run_until_complete(mark_queued())

        # 자동 재시도 (autoretry_for에 의해)
        raise


def _notify_reward_failure(
    task_id: str,
    user_id: str,
    category: str,
    error: str,
) -> None:
    """리워드 최종 실패 시 알림 발송.

    TODO: Slack/PagerDuty 연동
    """
    logger.critical(
        f"[REWARD_DLQ] task_id={task_id}, user_id={user_id}, " f"category={category}, error={error}"
    )
    # 추후 Slack webhook 등 연동
    # slack_webhook.send(f"⚠️ Reward DLQ: {task_id}")


@celery_app.task(
    name="domains.scan.tasks.reward.process_dlq",
    bind=True,
)
def process_dlq(self) -> dict:
    """DLQ에서 실패한 리워드를 재처리합니다.

    주기적 스케줄러(Celery Beat)에서 호출되거나 수동으로 실행합니다.

    Returns:
        재처리 결과 요약
    """
    # TODO: DLQ 메시지 조회 및 재처리 로직
    # RabbitMQ Dead Letter Exchange에서 메시지를 가져와 재시도
    logger.info("Processing reward DLQ...")

    # 구현 예시:
    # 1. DLQ에서 메시지 조회
    # 2. 각 메시지에 대해 reward_grant 재발행
    # 3. 결과 집계 및 반환

    return {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
    }
