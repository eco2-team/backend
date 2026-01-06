"""ClassifyPipeline - 파이프라인 오케스트레이션.

Application Layer에서 유스케이스 조합 담당.
단계 순서, fallback, retry 정책 관리.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scan_worker.application.classify.ports.event_publisher import (
    EventPublisherPort,
)
from scan_worker.application.common.step_interface import Step

if TYPE_CHECKING:
    from scan_worker.application.classify.dto.classify_context import (
        ClassifyContext,
    )
    from scan_worker.application.classify.ports.context_store import (
        ContextStorePort,
    )

logger = logging.getLogger(__name__)


class ClassifyPipeline:
    """Classify 파이프라인 - 단계 조합(순서, fallback, retry).

    Application Layer에서 유스케이스 오케스트레이션 담당.
    각 Step을 순서대로 실행하며 이벤트 발행.
    """

    def __init__(
        self,
        steps: list[tuple[str, Step]],
        event_publisher: EventPublisherPort,
    ):
        """초기화.

        Args:
            steps: [(name, step), ...] 형태의 단계 리스트
            event_publisher: 이벤트 발행 Port
        """
        self._steps = steps
        self._events = event_publisher

    def execute(self, ctx: "ClassifyContext") -> "ClassifyContext":
        """파이프라인 실행.

        Usecase가 "단계 리스트"를 순서대로 실행.
        Context만 공유 → 모듈 의존이 아닌 데이터 흐름.

        Args:
            ctx: 입력 Context

        Returns:
            최종 Context (모든 단계 결과 포함)
        """
        logger.info(
            "ClassifyPipeline started",
            extra={"task_id": ctx.task_id, "user_id": ctx.user_id},
        )

        for name, step in self._steps:
            try:
                # Step 시작 이벤트
                self._events.publish_stage_event(
                    task_id=ctx.task_id,
                    stage=name,
                    status="started",
                    progress=ctx.progress,
                )

                # Step 실행
                ctx = step.run(ctx)

                # Step 완료 이벤트
                self._events.publish_stage_event(
                    task_id=ctx.task_id,
                    stage=name,
                    status="completed",
                    progress=ctx.progress,
                )

            except Exception as e:
                ctx.error = str(e)
                logger.error(
                    "ClassifyPipeline step failed",
                    extra={
                        "task_id": ctx.task_id,
                        "stage": name,
                        "error": str(e),
                    },
                    exc_info=True,
                )

                # Step 실패 이벤트
                self._events.publish_stage_event(
                    task_id=ctx.task_id,
                    stage=name,
                    status="failed",
                    progress=ctx.progress,
                    result={"error": str(e)},
                )
                break

        logger.info(
            "ClassifyPipeline completed",
            extra={
                "task_id": ctx.task_id,
                "progress": ctx.progress,
                "error": ctx.error,
            },
        )

        return ctx


class SingleStepRunner:
    """단일 Step 실행기.

    기존 Celery Chain 구조와 호환성 유지.
    각 Task에서 개별 Step만 실행.
    """

    def __init__(self, event_publisher: EventPublisherPort):
        """초기화.

        Args:
            event_publisher: 이벤트 발행 Port
        """
        self._events = event_publisher

    def run_step(
        self,
        step: Step,
        step_name: str,
        ctx: "ClassifyContext",
    ) -> "ClassifyContext":
        """단일 Step 실행.

        Args:
            step: 실행할 Step
            step_name: Step 이름 (이벤트 발행용)
            ctx: 입력 Context

        Returns:
            업데이트된 Context
        """
        try:
            # Step 시작 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="started",
                progress=ctx.progress,
            )

            # Step 실행
            ctx = step.run(ctx)

            # Step 완료 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="completed",
                progress=ctx.progress,
            )

        except Exception as e:
            ctx.error = str(e)

            # Step 실패 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="failed",
                progress=ctx.progress,
                result={"error": str(e)},
            )
            raise

        return ctx


class CheckpointingStepRunner:
    """체크포인팅 기능이 추가된 Step 실행기.

    Stateless Reducer 패턴의 재현성(Reproducibility) 보장.
    각 Step 완료 시 Context를 저장하여 실패 복구 지원.

    Benefits:
    - 이미 완료된 Step은 건너뜀 (멱등성)
    - 실패 시 마지막 체크포인트부터 재시작
    - LLM 재호출 비용 절감
    """

    def __init__(
        self,
        event_publisher: EventPublisherPort,
        context_store: "ContextStorePort",
        skip_completed: bool = True,
    ):
        """초기화.

        Args:
            event_publisher: 이벤트 발행 Port
            context_store: Context 저장소 Port (체크포인팅)
            skip_completed: 이미 완료된 Step 건너뛰기 여부
        """
        self._events = event_publisher
        self._store = context_store
        self._skip_completed = skip_completed

    def run_step(
        self,
        step: Step,
        step_name: str,
        ctx: "ClassifyContext",
    ) -> "ClassifyContext":
        """단일 Step 실행 (체크포인팅 포함).

        Args:
            step: 실행할 Step
            step_name: Step 이름 (이벤트 발행용)
            ctx: 입력 Context

        Returns:
            업데이트된 Context
        """
        from scan_worker.application.classify.dto.classify_context import (
            ClassifyContext,
        )

        # 1. 체크포인트 확인 (이미 완료된 Step인지)
        if self._skip_completed:
            checkpoint = self._store.get_checkpoint(ctx.task_id, step_name)
            if checkpoint:
                logger.info(
                    "Step skipped - checkpoint exists",
                    extra={"task_id": ctx.task_id, "step": step_name},
                )
                return ClassifyContext.from_dict(checkpoint)

        try:
            # 2. Step 시작 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="started",
                progress=ctx.progress,
            )

            # 3. Step 실행
            ctx = step.run(ctx)

            # 4. 체크포인트 저장 (Step 완료 후)
            self._store.save_checkpoint(ctx.task_id, step_name, ctx.to_dict())

            # 5. Step 완료 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="completed",
                progress=ctx.progress,
            )

        except Exception as e:
            ctx.error = str(e)

            # Step 실패 이벤트
            self._events.publish_stage_event(
                task_id=ctx.task_id,
                stage=step_name,
                status="failed",
                progress=ctx.progress,
                result={"error": str(e)},
            )
            raise

        return ctx

    def resume_from_checkpoint(
        self,
        task_id: str,
    ) -> "ClassifyContext | None":
        """마지막 체크포인트에서 Context 복원.

        Args:
            task_id: 작업 ID

        Returns:
            복원된 Context (없으면 None)
        """
        from scan_worker.application.classify.dto.classify_context import (
            ClassifyContext,
        )

        result = self._store.get_latest_checkpoint(task_id)
        if result:
            step_name, ctx_dict = result
            logger.info(
                "Resuming from checkpoint",
                extra={"task_id": task_id, "step": step_name},
            )
            return ClassifyContext.from_dict(ctx_dict)
        return None

    def clear_checkpoints(self, task_id: str) -> None:
        """작업 완료 후 체크포인트 정리.

        Args:
            task_id: 작업 ID
        """
        self._store.clear_checkpoints(task_id)
