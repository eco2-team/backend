from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import List
from uuid import UUID, uuid4

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.scan.core.config import Settings, get_settings
from domains.scan.core.grpc_client import get_character_client
from domains.scan.core.validators import ImageUrlValidator
from domains.scan.database.session import get_db_session
from domains.scan.metrics import GRPC_CALL_COUNTER, GRPC_CALL_LATENCY
from domains.scan.models.scan_task import ScanTask as ScanTaskModel
from domains.scan.proto import character_pb2
from domains.scan.repositories.scan_task_repository import ScanTaskRepository
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)
from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains._shared.waste_pipeline.utils import ITEM_CLASS_PATH, load_yaml

DEFAULT_SCAN_PROMPT = "이 폐기물을 어떻게 분리배출해야 하나요?"
logger = logging.getLogger(__name__)


def get_scan_task_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ScanTaskRepository:
    """Factory for ScanTaskRepository with injected session."""
    return ScanTaskRepository(session)


class ScanService:
    _category_cache: List[ScanCategory] | None = None

    def __init__(
        self,
        settings: Settings = Depends(get_settings),
        repository: ScanTaskRepository = Depends(get_scan_task_repository),
    ):
        self.settings = settings
        self.repository = repository
        self.image_validator = ImageUrlValidator(settings)

    async def classify(
        self, payload: ClassificationRequest, user_id: UUID
    ) -> ClassificationResponse:
        """Classify waste image and return results."""
        image_url = str(payload.image_url) if payload.image_url else None

        if not image_url:
            return ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message="이미지 URL이 필요합니다.",
                error="IMAGE_URL_REQUIRED",
            )

        # Validate image URL (allowlist + SSRF prevention)
        validation = self.image_validator.validate(image_url)
        if not validation.valid:
            logger.warning(
                "Image URL validation failed",
                extra={
                    "url": image_url,
                    "error_code": validation.error.value if validation.error else None,
                    "error_message": validation.message,
                },
            )
            return ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message=validation.message or "이미지 URL 검증 실패",
                error=validation.error.value if validation.error else "VALIDATION_ERROR",
            )

        task_id = uuid4()
        log_ctx = {"task_id": str(task_id), "user_id": str(user_id)}

        logger.info("Scan pipeline started", extra=log_ctx)

        # Create task in DB with pending status
        try:
            await self.repository.create(
                task_id=task_id,
                user_id=user_id,
                image_url=image_url,
                user_input=payload.user_input,
            )
        except Exception:
            logger.exception("Failed to create scan task in DB", extra=log_ctx)
            return ClassificationResponse(
                task_id=str(task_id),
                status="failed",
                message="데이터베이스 저장에 실패했습니다.",
                error="DB_ERROR",
            )

        # Run AI pipeline
        pipeline_result, error = await self._run_pipeline(
            task_id, image_url, payload.user_input, log_ctx
        )

        if error:
            await self._handle_pipeline_failure(task_id, error, log_ctx)
            return ClassificationResponse(
                task_id=str(task_id),
                status="failed",
                message="분류 파이프라인 처리에 실패했습니다.",
                error=error,
            )

        # Process reward
        reward = await self._process_reward(task_id, user_id, pipeline_result, log_ctx)

        # Update task as completed
        classification = pipeline_result.classification_result.get("classification", {})
        category = classification.get("major_category")

        try:
            await self.repository.update_completed(
                task_id,
                category=category,
                confidence=None,
                pipeline_result=pipeline_result,
                reward=reward,
            )
        except Exception:
            logger.exception("Failed to update scan task in DB", extra=log_ctx)
            # Task completed but DB update failed - still return success to user
            # The data is in pipeline_result anyway

        logger.info("Scan pipeline completed", extra={**log_ctx, "category": category})

        return ClassificationResponse(
            task_id=str(task_id),
            status="completed",
            message="classification completed",
            pipeline_result=pipeline_result,
            reward=reward,
        )

    async def _run_pipeline(
        self,
        task_id: UUID,
        image_url: str,
        user_input: str | None,
        log_ctx: dict,
    ) -> tuple[WasteClassificationResult | None, str | None]:
        """Run AI classification pipeline. Returns (result, error)."""
        from domains.scan.metrics import PIPELINE_STEP_LATENCY

        pipeline_started = perf_counter()
        prompt_text = user_input or DEFAULT_SCAN_PROMPT

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Scan prompt text", extra={**log_ctx, "prompt": prompt_text})

        try:
            pipeline_payload = await asyncio.to_thread(
                process_waste_classification,
                prompt_text,
                image_url,
                save_result=False,
                verbose=False,
            )
        except PipelineError as exc:
            elapsed_ms = (perf_counter() - pipeline_started) * 1000
            logger.info(
                "Scan pipeline failed",
                extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
            )
            return None, str(exc)

        # Record metrics
        elapsed_ms = (perf_counter() - pipeline_started) * 1000
        metadata = pipeline_payload.get("metadata", {})
        if metadata:
            PIPELINE_STEP_LATENCY.labels(step="vision").observe(metadata.get("duration_vision", 0))
            PIPELINE_STEP_LATENCY.labels(step="rag").observe(metadata.get("duration_rag", 0))
            PIPELINE_STEP_LATENCY.labels(step="answer").observe(metadata.get("duration_answer", 0))
            PIPELINE_STEP_LATENCY.labels(step="total_pipeline").observe(
                metadata.get("duration_total", 0)
            )

        logger.info("Scan pipeline succeeded", extra={**log_ctx, "elapsed_ms": elapsed_ms})

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Scan pipeline raw payload",
                extra={
                    **log_ctx,
                    "payload": json.dumps(pipeline_payload, ensure_ascii=False),
                },
            )

        return WasteClassificationResult(**pipeline_payload), None

    async def _handle_pipeline_failure(self, task_id: UUID, error: str, log_ctx: dict) -> None:
        """Mark task as failed in DB."""
        try:
            await self.repository.update_failed(task_id, error_message=error)
        except Exception:
            logger.exception("Failed to update failed task in DB", extra=log_ctx)

    async def _process_reward(
        self,
        task_id: UUID,
        user_id: UUID,
        pipeline_result: WasteClassificationResult,
        log_ctx: dict,
    ) -> CharacterRewardResponse | None:
        """Process character reward if applicable."""
        from domains.scan.metrics import REWARD_MATCH_COUNTER, REWARD_MATCH_LATENCY

        if not self._should_attempt_reward(pipeline_result):
            REWARD_MATCH_COUNTER.labels(status="skipped").inc()
            return None

        reward = None
        with REWARD_MATCH_LATENCY.time():
            reward_request = self._build_reward_request(user_id, str(task_id), pipeline_result)
            if reward_request:
                reward = await self._call_character_reward_api(reward_request)

        if reward:
            REWARD_MATCH_COUNTER.labels(status="success").inc()
            logger.debug("Reward granted", extra={**log_ctx, "reward_name": reward.name})
        else:
            REWARD_MATCH_COUNTER.labels(status="failed").inc()

        return reward

    async def task(self, task_id: str) -> ScanTask:
        """Retrieve a scan task by ID."""
        try:
            task_uuid = UUID(task_id)
        except ValueError as exc:
            raise LookupError(f"invalid task_id format: {task_id}") from exc

        db_task = await self.repository.get_by_id(task_uuid)
        if db_task is None:
            raise LookupError(f"task {task_id} not found")

        return self._to_schema(db_task)

    async def categories(self) -> list[ScanCategory]:
        if ScanService._category_cache is None:
            ScanService._category_cache = self._load_categories()
        return ScanService._category_cache

    async def metrics(self) -> dict:
        completed = await self.repository.count_completed()
        last_completed = await self.repository.get_last_completed_at()
        categories = await self.categories()
        return {
            "completed_tasks": completed,
            "last_completed_at": last_completed.isoformat() if last_completed else None,
            "supported_categories": len(categories),
        }

    def _to_schema(self, db_task: ScanTaskModel) -> ScanTask:
        """Convert ORM model to Pydantic schema."""
        pipeline_result = None
        if db_task.pipeline_result:
            pipeline_result = WasteClassificationResult(**db_task.pipeline_result)

        reward = None
        if db_task.reward:
            reward = CharacterRewardResponse(**db_task.reward)

        return ScanTask(
            task_id=str(db_task.id),
            status=db_task.status,
            category=db_task.category,
            confidence=db_task.confidence,
            completed_at=db_task.completed_at,
            pipeline_result=pipeline_result,
            reward=reward,
        )

    def _load_categories(self) -> list[ScanCategory]:
        yaml_data = load_yaml(ITEM_CLASS_PATH) or {}
        item_classes = yaml_data.get("item_class_list", {})
        categories: list[ScanCategory] = []
        counter = 1
        for major, entries in item_classes.items():
            instructions: List[str] = []
            if isinstance(entries, dict):
                for group, items in entries.items():
                    instructions.append(f"{group}: {', '.join(items)}")
            categories.append(
                ScanCategory(
                    id=counter,
                    name=str(major),
                    display_name=str(major),
                    instructions=instructions or ["세부 분류 정보 없음"],
                )
            )
            counter += 1
        return categories

    @staticmethod
    def _extract_classification(
        result: WasteClassificationResult,
    ) -> tuple[str, str, str | None]:
        """분류 결과에서 major, middle, minor 카테고리 추출."""
        payload = result.classification_result or {}
        classification = payload.get("classification", {}) or {}
        major = (classification.get("major_category") or "").strip()
        middle = (classification.get("middle_category") or "").strip()
        minor_raw = classification.get("minor_category")
        minor = (minor_raw or "").strip() or None
        return major, middle, minor

    def _should_attempt_reward(self, result: WasteClassificationResult) -> bool:
        if not self.settings.reward_feature_enabled:
            return False
        if self._has_insufficiencies(result):
            return False
        major, middle, _ = self._extract_classification(result)
        if not major or not middle:
            return False
        if major != "재활용폐기물":
            return False
        return bool(result.disposal_rules)

    def _build_reward_request(
        self,
        user_id: UUID,
        task_id: str,
        result: WasteClassificationResult,
    ) -> CharacterRewardRequest | None:
        major, middle, minor = self._extract_classification(result)
        if not major or not middle:
            return None

        payload = result.classification_result or {}
        situation_tags = payload.get("situation_tags", [])
        normalized_tags = [str(tag).strip() for tag in situation_tags if isinstance(tag, str)]

        return CharacterRewardRequest(
            source=CharacterRewardSource.SCAN,
            user_id=user_id,
            task_id=task_id,
            classification=ClassificationSummary(
                major_category=major,
                middle_category=middle,
                minor_category=minor,
            ),
            situation_tags=normalized_tags,
            disposal_rules_present=bool(result.disposal_rules),
            insufficiencies_present=self._has_insufficiencies(result),
        )

    async def _call_character_reward_api(
        self, reward_request: CharacterRewardRequest
    ) -> CharacterRewardResponse | None:
        """Call Character service gRPC API with retry and circuit breaker."""
        # Create Protobuf request
        classification_msg = character_pb2.ClassificationSummary(
            major_category=reward_request.classification.major_category,
            middle_category=reward_request.classification.middle_category,
        )
        if reward_request.classification.minor_category:
            classification_msg.minor_category = reward_request.classification.minor_category

        grpc_req = character_pb2.RewardRequest(
            source=reward_request.source.value,
            user_id=str(reward_request.user_id),
            task_id=reward_request.task_id,
            classification=classification_msg,
            situation_tags=reward_request.situation_tags,
            disposal_rules_present=reward_request.disposal_rules_present,
            insufficiencies_present=reward_request.insufficiencies_present,
        )

        log_ctx = {
            "task_id": reward_request.task_id,
            "user_id": str(reward_request.user_id),
        }

        # Call gRPC with retry and circuit breaker
        client = get_character_client()
        with GRPC_CALL_LATENCY.labels(service="character", method="GetCharacterReward").time():
            response = await client.get_character_reward(grpc_req, log_ctx)

        if response is None:
            GRPC_CALL_COUNTER.labels(
                service="character", method="GetCharacterReward", status="error"
            ).inc()
            return None

        # Convert Protobuf response to Pydantic model
        result = CharacterRewardResponse(
            received=response.received,
            already_owned=response.already_owned,
            name=response.name if response.HasField("name") else None,
            dialog=response.dialog if response.HasField("dialog") else None,
            match_reason=response.match_reason if response.HasField("match_reason") else None,
            character_type=(
                response.character_type if response.HasField("character_type") else None
            ),
            type=response.type if response.HasField("type") else None,
        )

        GRPC_CALL_COUNTER.labels(
            service="character", method="GetCharacterReward", status="success"
        ).inc()

        return result

    @staticmethod
    def _has_insufficiencies(result: WasteClassificationResult) -> bool:
        final_answer = result.final_answer or {}
        insufficiencies = final_answer.get("insufficiencies")
        if insufficiencies is None:
            return True
        for entry in insufficiencies:
            if isinstance(entry, str):
                if entry.strip():
                    return True
            elif entry:
                return True
        return False
