"""Classification pipeline tasks.

3단계 파이프라인을 Celery Chain으로 실행합니다:
1. vision_scan: GPT Vision 분석 (~3.5초)
2. rule_match: Rule-based RAG 매칭 (~1ms)
3. answer_gen: GPT Answer 생성 (~3.8초)
"""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any

from celery import chain

from domains._shared.taskqueue import TaskStatus, TaskStep, celery_app
from domains._shared.taskqueue.state import get_state_manager

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="domains.scan.tasks.classification.vision_scan",
    max_retries=2,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def vision_scan(self, task_id: str, image_url: str, user_input: str = "") -> dict[str, Any]:
    """Step 1: GPT Vision 분석.

    이미지를 분석하여 폐기물 분류 결과를 반환합니다.

    Args:
        task_id: 태스크 ID
        image_url: 분석할 이미지 URL
        user_input: 사용자 입력 텍스트 (선택)

    Returns:
        Vision 분석 결과 dict
    """
    import asyncio

    from domains._shared.waste_pipeline.vision import analyze_images

    logger.info(f"[{task_id}] Starting vision_scan")
    start = perf_counter()

    # 상태 업데이트 (비동기를 동기로 실행)
    async def update_state():
        manager = get_state_manager()
        await manager.update(
            task_id,
            status=TaskStatus.PROCESSING,
            step=TaskStep.SCAN,
            progress=15,
        )

    asyncio.get_event_loop().run_until_complete(update_state())

    try:
        # GPT Vision 분석 실행
        result = analyze_images(user_input, image_url)

        # dict로 변환
        if hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        elif isinstance(result, str):
            result_dict = json.loads(result)
        else:
            result_dict = dict(result) if result else {}

        duration = perf_counter() - start
        logger.info(f"[{task_id}] vision_scan completed in {duration:.2f}s")

        # 부분 결과 저장
        async def save_partial():
            manager = get_state_manager()
            await manager.update(
                task_id,
                progress=33,
                partial_result={
                    "classification": result_dict.get("classification", {}),
                    "situation_tags": result_dict.get("situation_tags", []),
                },
                metadata={"duration_scan": round(duration, 3)},
            )

        asyncio.get_event_loop().run_until_complete(save_partial())

        return {
            "task_id": task_id,
            "vision_result": result_dict,
            "user_input": user_input,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"[{task_id}] vision_scan failed: {error_msg}")

        async def mark_failed():
            manager = get_state_manager()
            await manager.update(
                task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                error_code="VISION_SCAN_FAILED",
            )

        asyncio.get_event_loop().run_until_complete(mark_failed())
        raise


@celery_app.task(
    bind=True,
    name="domains.scan.tasks.classification.rule_match",
    max_retries=3,
    default_retry_delay=1,
)
def rule_match(self, prev_result: dict[str, Any]) -> dict[str, Any]:
    """Step 2: Rule-based RAG 매칭.

    분류 결과에 맞는 배출 규정을 조회합니다.

    Args:
        prev_result: vision_scan 결과

    Returns:
        Vision 결과 + 배출 규정
    """
    import asyncio

    from domains._shared.waste_pipeline.rag import get_disposal_rules

    task_id = prev_result["task_id"]
    vision_result = prev_result["vision_result"]

    logger.info(f"[{task_id}] Starting rule_match")
    start = perf_counter()

    # 상태 업데이트
    async def update_state():
        manager = get_state_manager()
        await manager.update(
            task_id,
            step=TaskStep.ANALYZE,
            progress=50,
        )

    asyncio.get_event_loop().run_until_complete(update_state())

    try:
        # RAG 매칭 실행
        disposal_rules = get_disposal_rules(vision_result)

        if not disposal_rules:
            raise ValueError("매칭되는 배출 규정을 찾지 못했습니다.")

        duration = perf_counter() - start
        logger.info(f"[{task_id}] rule_match completed in {duration:.4f}s")

        # 상태 업데이트
        async def save_progress():
            manager = get_state_manager()
            await manager.update(
                task_id,
                progress=66,
                metadata={"duration_rag": round(duration, 4)},
            )

        asyncio.get_event_loop().run_until_complete(save_progress())

        return {
            **prev_result,
            "disposal_rules": disposal_rules,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"[{task_id}] rule_match failed: {error_msg}")

        async def mark_failed():
            manager = get_state_manager()
            await manager.update(
                task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                error_code="RULE_MATCH_FAILED",
            )

        asyncio.get_event_loop().run_until_complete(mark_failed())
        raise


@celery_app.task(
    bind=True,
    name="domains.scan.tasks.classification.answer_gen",
    max_retries=2,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def answer_gen(self, prev_result: dict[str, Any]) -> dict[str, Any]:
    """Step 3: GPT Answer 생성.

    분류 결과와 배출 규정을 바탕으로 사용자 안내문을 생성합니다.

    Args:
        prev_result: rule_match 결과

    Returns:
        전체 파이프라인 결과
    """
    import asyncio

    from domains._shared.waste_pipeline.answer import generate_answer

    task_id = prev_result["task_id"]
    vision_result = prev_result["vision_result"]
    disposal_rules = prev_result["disposal_rules"]

    logger.info(f"[{task_id}] Starting answer_gen")
    start = perf_counter()

    # 상태 업데이트
    async def update_state():
        manager = get_state_manager()
        await manager.update(
            task_id,
            step=TaskStep.ANSWER,
            progress=75,
        )

    asyncio.get_event_loop().run_until_complete(update_state())

    try:
        # Answer 생성 실행
        final_answer = generate_answer(vision_result, disposal_rules)

        # dict로 변환
        if hasattr(final_answer, "model_dump"):
            answer_dict = final_answer.model_dump()
        elif isinstance(final_answer, str):
            answer_dict = json.loads(final_answer)
        else:
            answer_dict = dict(final_answer) if final_answer else {}

        duration = perf_counter() - start
        logger.info(f"[{task_id}] answer_gen completed in {duration:.2f}s")

        # 전체 결과 구성
        full_result = {
            "classification_result": vision_result,
            "disposal_rules": disposal_rules,
            "final_answer": answer_dict,
        }

        # 완료 상태 저장
        async def mark_completed():
            manager = get_state_manager()
            await manager.update(
                task_id,
                status=TaskStatus.COMPLETED,
                step=TaskStep.COMPLETE,
                progress=100,
                result=full_result,
                metadata={"duration_answer": round(duration, 3)},
            )

        asyncio.get_event_loop().run_until_complete(mark_completed())

        # 리워드 태스크 발행 (분류 성공 시)
        from domains.scan.tasks.reward import reward_grant

        classification = vision_result.get("classification", {})
        major_category = classification.get("major_category")

        if major_category:
            # 별도의 상태 업데이트
            async def update_reward_status():
                manager = get_state_manager()
                state = await manager.get(task_id)
                if state:
                    reward_task = reward_grant.delay(
                        task_id=task_id,
                        user_id=state.user_id,
                        category=major_category,
                    )
                    await manager.update(
                        task_id,
                        reward_status="processing",
                        reward_task_id=reward_task.id,
                    )

            asyncio.get_event_loop().run_until_complete(update_reward_status())

        return {
            "task_id": task_id,
            "result": full_result,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.exception(f"[{task_id}] answer_gen failed: {error_msg}")

        async def mark_failed():
            manager = get_state_manager()
            await manager.update(
                task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                error_code="ANSWER_GEN_FAILED",
            )

        asyncio.get_event_loop().run_until_complete(mark_failed())
        raise


def run_classification_pipeline(
    task_id: str,
    image_url: str,
    user_input: str = "",
) -> str:
    """분류 파이프라인을 Celery Chain으로 실행합니다.

    Args:
        task_id: 태스크 ID
        image_url: 분석할 이미지 URL
        user_input: 사용자 입력 텍스트

    Returns:
        Celery AsyncResult ID
    """
    workflow = chain(
        vision_scan.s(task_id, image_url, user_input),
        rule_match.s(),
        answer_gen.s(),
    )

    result = workflow.apply_async()
    logger.info(f"[{task_id}] Classification pipeline started: {result.id}")

    return result.id
