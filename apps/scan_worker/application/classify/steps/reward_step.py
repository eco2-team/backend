"""Reward Step - 보상 처리 단계.

Stage 4: 캐릭터 매칭 + DB 저장 Task 발행 + 결과 캐싱.
Celery를 통해 character-worker, users-worker에 Task 발행.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from celery import Celery
from celery.exceptions import TimeoutError as CeleryTimeoutError

from scan_worker.application.classify.ports.event_publisher import (
    EventPublisherPort,
)
from scan_worker.application.classify.ports.result_cache import ResultCachePort
from scan_worker.application.common.step_interface import Step

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )

logger = logging.getLogger(__name__)

# 매칭 결과 대기 타임아웃 (초)
MATCH_TIMEOUT = int(os.getenv("CHARACTER_MATCH_TIMEOUT", "10"))


class RewardStep(Step):
    """보상 처리 Step - Celery Task 발행.

    1. character.match 호출 (동기 대기)
    2. character.save_ownership 발행 (Fire & Forget)
    3. users.save_character 발행 (Fire & Forget)
    4. 결과 캐시 저장
    5. done 이벤트 발행

    progress: 75 → 100
    """

    def __init__(
        self,
        celery_app: Celery,
        event_publisher: EventPublisherPort,
        result_cache: ResultCachePort,
    ):
        """초기화.

        Args:
            celery_app: Celery 앱 인스턴스
            event_publisher: 이벤트 발행 Port
            result_cache: 결과 캐시 Port
        """
        self._celery = celery_app
        self._events = event_publisher
        self._cache = result_cache

    def run(self, ctx: "ClassifyContext") -> "ClassifyContext":
        """Step 실행.

        Args:
            ctx: 입력 Context (모든 이전 단계 결과 필요)

        Returns:
            업데이트된 Context (reward 필드 채워짐)
        """
        start = time.perf_counter()

        logger.info(
            "RewardStep started",
            extra={"task_id": ctx.task_id, "user_id": ctx.user_id},
        )

        # 1. 보상 조건 확인
        reward = None
        if self._should_attempt_reward(ctx):
            # 2. character.match 호출 (동기 대기)
            reward = self._dispatch_character_match(ctx)

            # 3. DB 저장 Task 발행 (Fire & Forget)
            if reward and reward.get("received") and reward.get("character_id"):
                self._dispatch_save_tasks(ctx.user_id, reward)

        elapsed = (time.perf_counter() - start) * 1000

        # 4. 클라이언트용 응답 구성
        reward_response = None
        if reward:
            reward_response = {
                "name": reward.get("name"),
                "dialog": reward.get("dialog"),
                "match_reason": reward.get("match_reason"),
                "type": reward.get("type"),
            }

        # Context 업데이트
        ctx.reward = reward_response
        ctx.latencies["duration_reward_ms"] = elapsed
        ctx.progress = 100

        # 5. 결과 구성 (ClassificationResponse 스키마에 맞춤)
        done_result = {
            "task_id": ctx.task_id,
            "status": "completed",
            "message": "classification completed",
            "pipeline_result": {
                "classification_result": ctx.classification,
                "disposal_rules": ctx.disposal_rules,
                "final_answer": ctx.final_answer,
            },
            "reward": ctx.reward,
            "error": None,
        }

        # 6. 결과 캐시 저장 (Race Condition 방지: done 이벤트 전에 저장)
        self._cache.cache_result(ctx.task_id, done_result)

        # 7. done 이벤트 발행
        self._events.publish_stage_event(
            task_id=ctx.task_id,
            stage="done",
            status="completed",
            result=done_result,
        )

        logger.info(
            "RewardStep completed",
            extra={
                "task_id": ctx.task_id,
                "elapsed_ms": elapsed,
                "has_reward": reward_response is not None,
                "matched_character": reward_response.get("name") if reward_response else None,
            },
        )

        return ctx

    def _should_attempt_reward(self, ctx: "ClassifyContext") -> bool:
        """보상 평가 조건 확인."""
        reward_enabled = os.getenv("REWARD_FEATURE_ENABLED", "true").lower() == "true"
        if not reward_enabled:
            return False

        if not ctx.classification:
            return False

        classification = ctx.classification.get("classification", {})
        major = classification.get("major_category", "").strip()
        middle = classification.get("middle_category", "").strip()

        if not major or not middle:
            return False

        if major != "재활용폐기물":
            return False

        if not ctx.disposal_rules:
            return False

        # 미흡항목이 있으면 보상 불가
        if ctx.final_answer:
            insufficiencies = ctx.final_answer.get("insufficiencies", [])
            for entry in insufficiencies:
                if isinstance(entry, str) and entry.strip():
                    return False
                elif entry:
                    return False

        return True

    def _dispatch_character_match(self, ctx: "ClassifyContext") -> dict[str, Any] | None:
        """character.match Task 호출 (동기 대기).

        Fallback: 타임아웃/에러 시 None 반환 (SSE 완료 보장).

        ⚠️ routing_key만 사용 - task_create_missing_queues=False이므로
           queue= 사용 시 task_queues 검증 발생. AMQP default exchange는
           routing_key와 동일한 이름의 큐로 직접 라우팅.
        """
        try:
            async_result = self._celery.send_task(
                "character.match",
                kwargs={
                    "user_id": ctx.user_id,
                    "classification_result": ctx.classification,
                    "disposal_rules_present": bool(ctx.disposal_rules),
                },
                routing_key="character.match",
            )

            result = async_result.get(
                timeout=MATCH_TIMEOUT,
                disable_sync_subtasks=False,
            )

            logger.info(
                "Character match completed",
                extra={
                    "task_id": ctx.task_id,
                    "received": result.get("received") if result else False,
                    "character_name": result.get("name") if result else None,
                },
            )
            return result

        except CeleryTimeoutError:
            logger.warning(
                "Character match timeout",
                extra={"task_id": ctx.task_id, "timeout_seconds": MATCH_TIMEOUT},
            )
            return None

        except Exception as exc:
            logger.warning(
                "Character match failed",
                extra={"task_id": ctx.task_id, "error": str(exc)},
            )
            return None

    def _dispatch_save_tasks(self, user_id: str, reward: dict[str, Any]) -> None:
        """DB 저장 Task 발행 (Fire & Forget).

        - character.save_ownership: character DB 저장 (routing_key: character.save_ownership)
        - users.save_character: users DB 저장 (routing_key: users.save_character)

        ⚠️ routing_key만 사용 - AMQP default exchange 직접 라우팅
        """
        # character.save_ownership
        try:
            self._celery.send_task(
                "character.save_ownership",
                kwargs={
                    "user_id": user_id,
                    "character_id": reward["character_id"],
                    "character_code": reward.get("character_code", ""),
                    "source": "scan",
                },
                routing_key="character.save_ownership",
            )
            logger.info("save_ownership_task dispatched")
        except Exception:
            logger.exception("Failed to dispatch save_ownership_task")

        # users.save_character
        try:
            self._celery.send_task(
                "users.save_character",
                args=[
                    user_id,
                    reward["character_id"],
                    reward.get("character_code", ""),
                ],
                kwargs={
                    "character_name": reward.get("name", ""),
                    "character_type": reward.get("character_type"),
                    "source": "scan",
                },
                routing_key="users.save_character",
            )
            logger.info("save_users_character_task dispatched")
        except Exception:
            logger.exception("Failed to dispatch save_users_character_task")
