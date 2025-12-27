"""
Scan Reward Task

Celery Chain 기반 리워드 처리 (Pipeline Step 4)
- scan_reward_task: 보상 dispatch (character.match 호출 → fire & forget)

매칭은 character 도메인에서 처리하고, 결과를 받아 SSE로 반환합니다.
DB 저장은 character/my 도메인의 task에서 비동기로 처리됩니다.

Note:
    gevent pool 사용 시 블로킹 I/O가 자동으로 greenlet으로 전환됨.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis

from domains._shared.celery.base_task import BaseTask
from domains._shared.events import get_sync_redis_client, publish_stage_event
from domains.scan.celery_app import celery_app

logger = logging.getLogger(__name__)

# 결과 캐시 TTL (초)
RESULT_CACHE_TTL = int(os.getenv("SCAN_RESULT_CACHE_TTL", "3600"))  # 1시간

# 매칭 결과 대기 타임아웃 (초)
MATCH_TIMEOUT = int(os.getenv("CHARACTER_MATCH_TIMEOUT", "10"))


# ============================================================
# Scan Chain용 Reward Task (scan.reward) - Dispatch 역할
# ============================================================


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="scan.reward",
    queue="scan.reward",
    max_retries=3,
    soft_time_limit=30,
    time_limit=60,
)
def scan_reward_task(
    self: BaseTask,
    prev_result: dict[str, Any],
) -> dict[str, Any]:
    """Step 4: Reward Evaluation (Chain 마지막 단계).

    보상 매칭을 character 도메인에 위임하고 결과를 받아 응답합니다.
    DB 저장은 별도 task에서 비동기로 처리됩니다.

    Flow:
        1. 조건 검증 (_should_attempt_reward)
        2. character.match 호출 (동기 대기) → 매칭 결과
        3. 즉시 응답 (SSE로 클라이언트에게 전달)
        4. character.save_ownership, my.save_character 발행 (Fire & Forget)

    Note:
        gevent pool에서는 블로킹 get()이 greenlet으로 자동 전환됨.
    """
    task_id = prev_result.get("task_id")
    user_id = prev_result.get("user_id")
    classification_result = prev_result.get("classification_result", {})
    disposal_rules = prev_result.get("disposal_rules")
    final_answer = prev_result.get("final_answer", {})
    metadata = prev_result.get("metadata", {})
    category = prev_result.get("category")

    log_ctx = {
        "task_id": task_id,
        "user_id": user_id,
        "celery_task_id": self.request.id,
        "stage": "reward",
    }
    logger.info("Scan reward task started", extra=log_ctx)

    # Redis Streams: 시작 이벤트 발행
    redis_client = get_sync_redis_client()
    publish_stage_event(redis_client, task_id, "reward", "started", progress=75)

    # 1. 조건 확인
    reward = None
    if _should_attempt_reward(classification_result, disposal_rules, final_answer):
        # 2. character.match 호출 (동기 대기, gevent가 greenlet 전환)
        reward = _dispatch_character_match(
            user_id=user_id,
            classification_result=classification_result,
            disposal_rules_present=bool(disposal_rules),
            log_ctx=log_ctx,
        )

        # 3. DB 저장 task 발행 (Fire & Forget)
        if reward and reward.get("received") and reward.get("character_id"):
            _dispatch_save_tasks(
                user_id=user_id,
                reward=reward,
                log_ctx=log_ctx,
            )

    # 4. 최종 결과 구성 (내부용 필드 제거, 클라이언트 표시용만)
    reward_response = None
    if reward:
        reward_response = {
            "name": reward.get("name"),
            "dialog": reward.get("dialog"),
            "match_reason": reward.get("match_reason"),
            "type": reward.get("type"),
        }

    result = {
        **prev_result,
        "reward": reward_response,
    }

    logger.info(
        "scan_task_completed",
        extra={
            "event_type": "scan_completed",
            "task_id": task_id,
            "user_id": user_id,
            "category": category,
            "duration_total_ms": metadata.get("duration_total_ms"),
            "duration_vision_ms": metadata.get("duration_vision_ms"),
            "duration_rule_ms": metadata.get("duration_rule_ms"),
            "duration_answer_ms": metadata.get("duration_answer_ms"),
            "has_disposal_rules": disposal_rules is not None,
            "has_reward": reward_response is not None,
            "matched_character": reward_response.get("name") if reward_response else None,
        },
    )

    # Redis Streams: 완료 이벤트 발행 (결과 포함)
    publish_stage_event(
        redis_client,
        task_id,
        "reward",
        "completed",
        progress=100,
        result=result,
    )

    # done 이벤트용 결과 구성 (ClassificationResponse 스키마에 맞춤)
    done_result = {
        "task_id": task_id,
        "status": "completed",
        "message": "classification completed",
        "pipeline_result": {
            "classification_result": result.get("classification_result"),
            "disposal_rules": result.get("disposal_rules"),
            "final_answer": result.get("final_answer"),
        },
        "reward": result.get("reward"),
        "error": None,
    }

    # ⚠️ 순서 중요: Cache 저장 → done 이벤트 (Race Condition #2 방지)
    # done 이벤트를 받고 /result 호출 시 404 방지
    _cache_result(task_id, done_result)

    # Redis Streams: done 이벤트 발행 (결과 커밋 완료 신호)
    publish_stage_event(
        redis_client,
        task_id,
        "done",
        "completed",
        result=done_result,
    )

    # [Legacy] 커스텀 이벤트 발행 (Celery Events 방식, 마이그레이션 후 제거 예정)
    try:
        self.send_event(
            "task-result",
            result=result,
            task_id=task_id,
            root_id=task_id,
        )
        logger.debug("task_result_event_sent", extra={"task_id": task_id})
    except Exception as e:
        logger.warning(
            "task_result_event_failed",
            extra={"task_id": task_id, "error": str(e)},
        )

    return result


# ============================================================
# Helper Functions
# ============================================================


def _get_cache_redis_client() -> redis.Redis:
    """Cache Redis 클라이언트 (결과 저장용)."""
    cache_url = os.getenv(
        "REDIS_CACHE_URL", "redis://rfr-cache-redis.redis.svc.cluster.local:6379/0"
    )
    return redis.from_url(
        cache_url,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )


def _cache_result(task_id: str, result: dict[str, Any]) -> None:
    """결과를 Cache Redis에 저장."""
    cache_key = f"scan:result:{task_id}"
    try:
        client = _get_cache_redis_client()
        client.setex(cache_key, RESULT_CACHE_TTL, json.dumps(result))
        logger.debug("scan_result_cached", extra={"task_id": task_id, "ttl": RESULT_CACHE_TTL})
    except Exception as e:
        logger.warning(
            "scan_result_cache_failed",
            extra={"task_id": task_id, "error": str(e)},
        )


def _should_attempt_reward(
    classification_result: dict[str, Any],
    disposal_rules: dict | None,
    final_answer: dict[str, Any],
) -> bool:
    """리워드 평가 조건 확인."""
    reward_enabled = os.getenv("REWARD_FEATURE_ENABLED", "true").lower() == "true"
    if not reward_enabled:
        return False

    classification = classification_result.get("classification", {})
    major = classification.get("major_category", "").strip()
    middle = classification.get("middle_category", "").strip()

    if not major or not middle:
        return False

    if major != "재활용폐기물":
        return False

    if not disposal_rules:
        return False

    insufficiencies = final_answer.get("insufficiencies", [])
    for entry in insufficiencies:
        if isinstance(entry, str) and entry.strip():
            return False
        elif entry:
            return False

    return True


def _dispatch_character_match(
    user_id: str,
    classification_result: dict[str, Any],
    disposal_rules_present: bool,
    log_ctx: dict,
) -> dict[str, Any] | None:
    """character.match task 호출 (동기 대기).

    character-worker에서 로컬 캐시를 사용해 매칭 수행.
    gevent pool에서는 블로킹 get()이 자동으로 greenlet 전환됨.

    Fallback:
        - 타임아웃 시 None 반환 (SSE 완료 보장)
        - 에러 발생 시 None 반환 (전체 파이프라인 실패 방지)
    """
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    try:
        # send_task로 character.match 호출 (import 없이 이름으로)
        async_result = celery_app.send_task(
            "character.match",
            kwargs={
                "user_id": user_id,
                "classification_result": classification_result,
                "disposal_rules_present": disposal_rules_present,
            },
            queue="character.match",  # 빠른 응답용 전용 큐
        )

        # 동기 대기 (gevent가 greenlet으로 전환)
        result = async_result.get(
            timeout=MATCH_TIMEOUT,
            disable_sync_subtasks=False,
        )

        logger.info(
            "Character match completed",
            extra={
                **log_ctx,
                "received": result.get("received") if result else False,
                "character_name": result.get("name") if result else None,
            },
        )
        return result

    except CeleryTimeoutError:
        # Fallback: 타임아웃 시 None 반환 (전체 파이프라인 실패 방지)
        logger.warning(
            "Character match timeout - returning fallback",
            extra={
                **log_ctx,
                "timeout_seconds": MATCH_TIMEOUT,
                "fallback": "None (no reward)",
            },
        )
        return None

    except Exception as exc:
        # Fallback: 에러 시 None 반환 (전체 파이프라인 실패 방지)
        logger.warning(
            "Character match failed - returning fallback",
            extra={
                **log_ctx,
                "error": str(exc),
                "fallback": "None (no reward)",
            },
        )
        return None


def _dispatch_save_tasks(
    user_id: str,
    reward: dict[str, Any],
    log_ctx: dict,
) -> None:
    """DB 저장 task 발행 (Fire & Forget)."""
    dispatched = {"character": False, "my": False}

    # character.save_ownership → character.reward 큐
    try:
        celery_app.send_task(
            "character.save_ownership",
            kwargs={
                "user_id": user_id,
                "character_id": reward["character_id"],
                "source": "scan",
            },
            queue="character.reward",
        )
        dispatched["character"] = True
        logger.info("save_ownership_task dispatched", extra=log_ctx)
    except Exception:
        logger.exception("Failed to dispatch save_ownership_task", extra=log_ctx)

    # my.save_character → my.reward 큐
    try:
        celery_app.send_task(
            "my.save_character",
            kwargs={
                "user_id": user_id,
                "character_id": reward["character_id"],
                "character_code": reward.get("character_code", ""),
                "character_name": reward.get("name", ""),
                "character_type": reward.get("character_type"),
                "character_dialog": reward.get("dialog"),
                "source": "scan",
            },
            queue="my.reward",
        )
        dispatched["my"] = True
        logger.info("save_my_character_task dispatched", extra=log_ctx)
    except Exception:
        logger.exception("Failed to dispatch save_my_character_task", extra=log_ctx)

    logger.info(
        "Reward storage tasks dispatched",
        extra={
            **log_ctx,
            "character_id": reward["character_id"],
            "dispatched": dispatched,
        },
    )
