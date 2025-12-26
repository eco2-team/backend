from __future__ import annotations

import asyncio
import json
import logging
from time import perf_counter
from typing import List
from uuid import UUID, uuid4

from fastapi import Depends

from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.scan.core.config import Settings, get_settings
from domains.scan.core.grpc_client import get_character_client
from domains.scan.core.validators import ImageUrlValidator
from domains.scan.metrics import GRPC_CALL_COUNTER, GRPC_CALL_LATENCY
from domains.scan.proto import character_pb2
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
)
from domains._shared.events import get_async_redis_client
from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains._shared.waste_pipeline.utils import ITEM_CLASS_PATH, load_yaml

DEFAULT_SCAN_PROMPT = "이 폐기물을 어떻게 분리배출해야 하나요?"
logger = logging.getLogger(__name__)


class ScanService:
    """Scan Service - DB 없이 로그 기반 추적.

    모든 task 진행 정보와 결과는 구조화된 로그로 출력되어
    EFK 파이프라인(Fluent Bit → Elasticsearch)으로 수집됩니다.
    """

    _category_cache: List[ScanCategory] | None = None

    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings
        self.image_validator = ImageUrlValidator(settings)

    def _validate_request(
        self, payload: ClassificationRequest
    ) -> tuple[str | None, ClassificationResponse | None]:
        """요청 검증. (image_url, error_response) 반환."""
        image_url = str(payload.image_url) if payload.image_url else None

        if not image_url:
            return None, ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message="이미지 URL이 필요합니다.",
                error="IMAGE_URL_REQUIRED",
            )

        validation = self.image_validator.validate(image_url)
        if not validation.valid:
            logger.warning(
                "image_url_validation_failed",
                extra={
                    "event_type": "scan_validation_failed",
                    "url": image_url,
                    "error_code": validation.error.value if validation.error else None,
                    "error_message": validation.message,
                },
            )
            return None, ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message=validation.message or "이미지 URL 검증 실패",
                error=validation.error.value if validation.error else "VALIDATION_ERROR",
            )

        return image_url, None

    async def classify_sync(
        self, payload: ClassificationRequest, user_id: UUID
    ) -> ClassificationResponse:
        """동기 방식으로 폐기물 분류 (즉시 결과 반환)."""
        image_url, error = self._validate_request(payload)
        if error:
            return error

        task_id = uuid4()
        log_ctx = {"task_id": str(task_id), "user_id": str(user_id)}

        logger.info(
            "scan_task_created",
            extra={
                "event_type": "scan_created",
                "task_id": str(task_id),
                "user_id": str(user_id),
                "image_url": image_url,
                "user_input": payload.user_input,
                "mode": "sync",
            },
        )

        return await self._classify_sync_internal(
            task_id, user_id, image_url, payload.user_input, log_ctx
        )

    async def _classify_sync_internal(
        self,
        task_id: UUID,
        user_id: UUID,
        image_url: str,
        user_input: str | None,
        log_ctx: dict,
    ) -> ClassificationResponse:
        """동기 처리 방식."""
        pipeline_result, error = await self._run_pipeline(task_id, image_url, user_input, log_ctx)

        if error:
            logger.info(
                "scan_task_failed",
                extra={
                    "event_type": "scan_failed",
                    "task_id": str(task_id),
                    "user_id": str(user_id),
                    "error": error,
                },
            )
            return ClassificationResponse(
                task_id=str(task_id),
                status="failed",
                message="분류 파이프라인 처리에 실패했습니다.",
                error=error,
            )

        reward = await self._process_reward(task_id, user_id, pipeline_result, log_ctx)

        classification = pipeline_result.classification_result.get("classification", {})
        category = classification.get("major_category")
        # metadata는 classification_result 내부에 있거나 없을 수 있음
        metadata = pipeline_result.classification_result.get("metadata", {})

        # 완료 로그 (EFK로 수집)
        logger.info(
            "scan_task_completed",
            extra={
                "event_type": "scan_completed",
                "task_id": str(task_id),
                "user_id": str(user_id),
                "category": category,
                "middle_category": classification.get("middle_category"),
                "duration_total_ms": metadata.get("duration_total"),
                "duration_vision_ms": metadata.get("duration_vision"),
                "duration_rag_ms": metadata.get("duration_rag"),
                "duration_answer_ms": metadata.get("duration_answer"),
                "has_disposal_rules": pipeline_result.disposal_rules is not None,
                "has_reward": reward is not None,
                "reward_received": reward.received if reward else None,
            },
        )

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
        """Run AI classification pipeline."""
        from domains.scan.metrics import PIPELINE_STEP_LATENCY

        pipeline_started = perf_counter()
        prompt_text = user_input or DEFAULT_SCAN_PROMPT

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
                "scan_pipeline_error",
                extra={**log_ctx, "elapsed_ms": elapsed_ms, "error": str(exc)},
            )
            return None, str(exc)

        elapsed_ms = (perf_counter() - pipeline_started) * 1000
        metadata = pipeline_payload.get("metadata", {})
        if metadata:
            PIPELINE_STEP_LATENCY.labels(step="vision").observe(metadata.get("duration_vision", 0))
            PIPELINE_STEP_LATENCY.labels(step="rag").observe(metadata.get("duration_rag", 0))
            PIPELINE_STEP_LATENCY.labels(step="answer").observe(metadata.get("duration_answer", 0))
            PIPELINE_STEP_LATENCY.labels(step="total_pipeline").observe(
                metadata.get("duration_total", 0)
            )

        return WasteClassificationResult(**pipeline_payload), None

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
        else:
            REWARD_MATCH_COUNTER.labels(status="failed").inc()

        return reward

    async def categories(self) -> list[ScanCategory]:
        """지원하는 폐기물 카테고리 목록."""
        if ScanService._category_cache is None:
            ScanService._category_cache = self._load_categories()
        return ScanService._category_cache

    async def metrics(self) -> dict:
        """서비스 메트릭 (Prometheus metrics 기반)."""
        categories = await self.categories()
        return {
            "supported_categories": len(categories),
            "note": "상세 메트릭은 /metrics 엔드포인트 또는 Kibana에서 확인",
        }

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
        """Call Character service gRPC API."""
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

        client = get_character_client()
        with GRPC_CALL_LATENCY.labels(service="character", method="GetCharacterReward").time():
            response = await client.get_character_reward(grpc_req, log_ctx)

        if response is None:
            GRPC_CALL_COUNTER.labels(
                service="character", method="GetCharacterReward", status="error"
            ).inc()
            return None

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

    async def get_result(self, job_id: str) -> ClassificationResponse | None:
        """Redis Cache에서 작업 결과 조회.

        Args:
            job_id: 작업 ID (Celery task ID)

        Returns:
            ClassificationResponse if found, None otherwise
        """
        redis_client = await get_async_redis_client()
        cache_key = f"scan:result:{job_id}"

        try:
            cached = await redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                return ClassificationResponse(**data)
        except Exception as e:
            logger.warning(
                "scan_result_cache_error",
                extra={"job_id": job_id, "error": str(e)},
            )

        return None

    # Alias for backward compatibility with tests
    async def classify(
        self, payload: ClassificationRequest, user_id: UUID
    ) -> ClassificationResponse:
        """Alias for classify_sync (backward compatibility)."""
        return await self.classify_sync(payload, user_id)
