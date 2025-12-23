"""
DLQ (Dead Letter Queue) 재처리 Celery Tasks

Celery Beat를 통해 주기적으로 DLQ에서 실패한 메시지를 꺼내 재처리합니다.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

# 재시도 최대 횟수 (이후 Archive Queue로 이동)
MAX_RETRY_COUNT = 3

# RabbitMQ 연결을 위한 지연 임포트
_connection = None


def _get_rabbitmq_connection():
    """RabbitMQ 연결 가져오기 (싱글톤)."""
    global _connection
    if _connection is None or _connection.is_closed:
        import os
        import pika

        broker_url = os.environ.get("CELERY_BROKER_URL", "")
        params = pika.URLParameters(broker_url)
        _connection = pika.BlockingConnection(params)
    return _connection


def _get_retry_count(properties) -> int:
    """메시지 헤더에서 재시도 횟수 추출."""
    if not properties or not properties.headers:
        return 0
    return properties.headers.get("x-dlq-retry-count", 0)


def _increment_retry_header(properties) -> dict:
    """재시도 헤더 증가."""
    headers = dict(properties.headers) if properties and properties.headers else {}
    headers["x-dlq-retry-count"] = headers.get("x-dlq-retry-count", 0) + 1
    return headers


def _reprocess_dlq_generic(
    dlq_name: str,
    target_queue: str,
    archive_queue: str,
    task_module: str,
    task_name: str,
    max_messages: int = 10,
) -> dict[str, Any]:
    """범용 DLQ 재처리 로직.

    Args:
        dlq_name: DLQ 큐 이름
        target_queue: 재처리 대상 큐 이름
        archive_queue: 최대 재시도 초과 시 보관 큐
        task_module: Task 모듈 경로
        task_name: Task 이름 (로깅용)
        max_messages: 한 번에 처리할 최대 메시지 수

    Returns:
        처리 결과 통계
    """
    import pika

    stats = {
        "processed": 0,
        "retried": 0,
        "archived": 0,
        "errors": 0,
    }

    try:
        conn = _get_rabbitmq_connection()
        channel = conn.channel()
    except Exception as exc:
        logger.error(f"RabbitMQ 연결 실패: {exc}")
        stats["errors"] = 1
        return stats

    try:
        for _ in range(max_messages):
            method, properties, body = channel.basic_get(queue=dlq_name, auto_ack=False)

            if method is None:
                # 큐에 메시지 없음
                break

            stats["processed"] += 1
            retry_count = _get_retry_count(properties)

            try:
                if retry_count >= MAX_RETRY_COUNT:
                    # Archive Queue로 이동
                    headers = _increment_retry_header(properties)
                    channel.basic_publish(
                        exchange="",
                        routing_key=archive_queue,
                        body=body,
                        properties=pika.BasicProperties(
                            headers=headers,
                            delivery_mode=2,  # persistent
                        ),
                    )
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    stats["archived"] += 1
                    logger.warning(
                        "DLQ 메시지 아카이브",
                        extra={
                            "dlq": dlq_name,
                            "archive": archive_queue,
                            "retry_count": retry_count,
                        },
                    )
                else:
                    # 원래 큐로 재발행
                    headers = _increment_retry_header(properties)
                    channel.basic_publish(
                        exchange="",
                        routing_key=target_queue,
                        body=body,
                        properties=pika.BasicProperties(
                            headers=headers,
                            delivery_mode=2,
                        ),
                    )
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    stats["retried"] += 1
                    logger.info(
                        "DLQ 메시지 재처리",
                        extra={
                            "dlq": dlq_name,
                            "target": target_queue,
                            "retry_count": retry_count + 1,
                        },
                    )
            except Exception as exc:
                # 개별 메시지 처리 실패 시 nack하고 다음으로
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                stats["errors"] += 1
                logger.error(f"DLQ 메시지 재처리 실패: {exc}")

    except Exception as exc:
        logger.error(f"DLQ 재처리 중 오류: {exc}")
        stats["errors"] += 1
    finally:
        try:
            channel.close()
        except Exception:
            pass

    return stats


@shared_task(name="dlq.reprocess_scan_vision")
def reprocess_dlq_scan_vision(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 scan.vision 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for scan.vision")
    return _reprocess_dlq_generic(
        dlq_name="dlq.scan.vision",
        target_queue="scan.vision",
        archive_queue="archive.scan.vision",
        task_module="domains.scan.tasks.vision",
        task_name="vision_task",
        max_messages=max_messages,
    )


@shared_task(name="dlq.reprocess_scan_rule")
def reprocess_dlq_scan_rule(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 scan.rule 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for scan.rule")
    return _reprocess_dlq_generic(
        dlq_name="dlq.scan.rule",
        target_queue="scan.rule",
        archive_queue="archive.scan.rule",
        task_module="domains.scan.tasks.rule",
        task_name="rule_task",
        max_messages=max_messages,
    )


@shared_task(name="dlq.reprocess_scan_answer")
def reprocess_dlq_scan_answer(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 scan.answer 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for scan.answer")
    return _reprocess_dlq_generic(
        dlq_name="dlq.scan.answer",
        target_queue="scan.answer",
        archive_queue="archive.scan.answer",
        task_module="domains.scan.tasks.answer",
        task_name="answer_task",
        max_messages=max_messages,
    )


@shared_task(name="dlq.reprocess_scan_reward")
def reprocess_dlq_scan_reward(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 scan.reward 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for scan.reward")
    return _reprocess_dlq_generic(
        dlq_name="dlq.scan.reward",
        target_queue="scan.reward",
        archive_queue="archive.scan.reward",
        task_module="domains.scan.tasks.reward",
        task_name="scan_reward_task",
        max_messages=max_messages,
    )


@shared_task(name="dlq.reprocess_character_reward")
def reprocess_dlq_character_reward(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 character.reward 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for character.reward")
    return _reprocess_dlq_generic(
        dlq_name="dlq.character.reward",
        target_queue="character.reward",
        archive_queue="archive.character.reward",
        task_module="domains.character.tasks.reward",
        task_name="save_ownership_task",
        max_messages=max_messages,
    )


@shared_task(name="dlq.reprocess_my_reward")
def reprocess_dlq_my_reward(max_messages: int = 10) -> dict[str, Any]:
    """DLQ에서 my.reward 실패 메시지 재처리."""
    logger.info("Starting DLQ reprocess for my.reward")
    return _reprocess_dlq_generic(
        dlq_name="dlq.my.reward",
        target_queue="my.reward",
        archive_queue="archive.my.reward",
        task_module="domains.my.tasks.sync_character",
        task_name="save_my_character_task",
        max_messages=max_messages,
    )


# Beat 스케줄 설정 (Celery Config에서 사용)
BEAT_SCHEDULE = {
    "reprocess-dlq-scan-vision": {
        "task": "dlq.reprocess_scan_vision",
        "schedule": 300.0,  # 5분마다
        "kwargs": {"max_messages": 10},
    },
    "reprocess-dlq-scan-rule": {
        "task": "dlq.reprocess_scan_rule",
        "schedule": 300.0,
        "kwargs": {"max_messages": 10},
    },
    "reprocess-dlq-scan-answer": {
        "task": "dlq.reprocess_scan_answer",
        "schedule": 300.0,
        "kwargs": {"max_messages": 10},
    },
    "reprocess-dlq-scan-reward": {
        "task": "dlq.reprocess_scan_reward",
        "schedule": 300.0,
        "kwargs": {"max_messages": 10},
    },
    "reprocess-dlq-character-reward": {
        "task": "dlq.reprocess_character_reward",
        "schedule": 300.0,
        "kwargs": {"max_messages": 10},
    },
    "reprocess-dlq-my-reward": {
        "task": "dlq.reprocess_my_reward",
        "schedule": 300.0,
        "kwargs": {"max_messages": 10},
    },
}
