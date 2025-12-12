from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Dict, List
from uuid import UUID, uuid4

import httpx
from fastapi import Depends
from pydantic import ValidationError

from domains.character.schemas.reward import (
    CharacterRewardRequest,
    CharacterRewardResponse,
    CharacterRewardSource,
    ClassificationSummary,
)
from domains.scan.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)
from domains.scan.core.config import Settings, get_settings
from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains._shared.waste_pipeline.utils import ITEM_CLASS_PATH, load_yaml

DEFAULT_SCAN_PROMPT = "이 폐기물을 어떻게 분리배출해야 하나요?"
_TASK_STORE: Dict[str, ScanTask] = {}
logger = logging.getLogger(__name__)


class ScanService:
    _category_cache: List[ScanCategory] | None = None

    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings
        self._reward_endpoint = self._build_reward_endpoint()

    async def classify(
        self, payload: ClassificationRequest, user_id: UUID
    ) -> ClassificationResponse:
        image_url = str(payload.image_url) if payload.image_url else None

        if not image_url:
            return ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message="이미지 URL이 필요합니다.",
                error="IMAGE_URL_REQUIRED",
            )

        task_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        logger.info(
            "Scan pipeline started at %s (task_id=%s, user_id=%s)",
            started_at.isoformat(),
            task_id,
            user_id,
        )
        pipeline_started = perf_counter()
        prompt_text = payload.user_input or DEFAULT_SCAN_PROMPT
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Scan prompt text (task_id=%s): %s",
                task_id,
                prompt_text,
            )
        try:
            pipeline_payload = await asyncio.to_thread(
                process_waste_classification,
                prompt_text,
                image_url,
                save_result=False,
                verbose=False,
            )
        except PipelineError as exc:
            finished_at = datetime.now(timezone.utc)
            elapsed_ms = (perf_counter() - pipeline_started) * 1000
            logger.info(
                "Scan pipeline finished at %s (task_id=%s, %.1f ms, success=False)",
                finished_at.isoformat(),
                task_id,
                elapsed_ms,
            )
            return ClassificationResponse(
                task_id=task_id,
                status="failed",
                message="분류 파이프라인 처리에 실패했습니다.",
                error=str(exc),
            )

        # Record metrics
        from domains.scan.metrics import (
            PIPELINE_STEP_LATENCY,
            REWARD_MATCH_LATENCY,
            REWARD_MATCH_COUNTER,
        )

        metadata = pipeline_payload.get("metadata", {})
        if metadata:
            PIPELINE_STEP_LATENCY.labels(step="vision").observe(metadata.get("duration_vision", 0))
            PIPELINE_STEP_LATENCY.labels(step="rag").observe(metadata.get("duration_rag", 0))
            PIPELINE_STEP_LATENCY.labels(step="answer").observe(metadata.get("duration_answer", 0))
            PIPELINE_STEP_LATENCY.labels(step="total_pipeline").observe(
                metadata.get("duration_total", 0)
            )

        finished_at = datetime.now(timezone.utc)
        elapsed_ms = (perf_counter() - pipeline_started) * 1000
        logger.info(
            "Scan pipeline finished at %s (task_id=%s, %.1f ms, success=True)",
            finished_at.isoformat(),
            task_id,
            elapsed_ms,
        )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Scan pipeline raw payload (task_id=%s): %s",
                task_id,
                json.dumps(pipeline_payload, ensure_ascii=False),
            )

        pipeline_result = WasteClassificationResult(**pipeline_payload)
        classification = pipeline_result.classification_result.get("classification", {})
        category = classification.get("major_category")
        completed_at = datetime.now(timezone.utc)

        reward = None
        if self._should_attempt_reward(pipeline_result):
            with REWARD_MATCH_LATENCY.time():
                reward_request = self._build_reward_request(
                    user_id,
                    task_id,
                    pipeline_result,
                )
                if reward_request:
                    reward = await self._call_character_reward_api(reward_request)

            if reward:
                REWARD_MATCH_COUNTER.labels(status="success").inc()
            else:
                REWARD_MATCH_COUNTER.labels(status="failed").inc()
        else:
            REWARD_MATCH_COUNTER.labels(status="skipped").inc()

        task = ScanTask(
            task_id=task_id,
            status="completed",
            category=category,
            confidence=None,
            completed_at=completed_at,
            pipeline_result=pipeline_result,
            reward=reward,
        )
        _TASK_STORE[task_id] = task

        return ClassificationResponse(
            task_id=task_id,
            status="completed",
            message="classification completed",
            pipeline_result=pipeline_result,
            reward=reward,
        )

    async def task(self, task_id: str) -> ScanTask:
        try:
            return _TASK_STORE[task_id]
        except KeyError as exc:
            raise LookupError(f"task {task_id} not found") from exc

    async def categories(self) -> list[ScanCategory]:
        if ScanService._category_cache is None:
            ScanService._category_cache = self._load_categories()
        return ScanService._category_cache

    async def metrics(self) -> dict:
        completed = len(_TASK_STORE)
        last_completed = max(
            (task.completed_at for task in _TASK_STORE.values() if task.completed_at),
            default=None,
        )
        categories = await self.categories()
        return {
            "completed_tasks": completed,
            "last_completed_at": last_completed.isoformat() if last_completed else None,
            "supported_categories": len(categories),
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

    def _should_attempt_reward(self, result: WasteClassificationResult) -> bool:
        if not self.settings.reward_feature_enabled:
            return False
        if self._has_insufficiencies(result):
            return False
        classification_payload = result.classification_result or {}
        classification = classification_payload.get("classification", {})
        major = (classification.get("major_category") or "").strip()
        middle = (classification.get("middle_category") or "").strip()
        if not major or not middle:
            return False
        if major != "재활용폐기물":
            return False
        if not result.disposal_rules:
            return False
        return True

    def _build_reward_request(
        self,
        user_id: UUID,
        task_id: str,
        result: WasteClassificationResult,
    ) -> CharacterRewardRequest | None:
        classification_payload = result.classification_result or {}
        classification = classification_payload.get("classification", {}) or {}
        major = (classification.get("major_category") or "").strip()
        middle = (classification.get("middle_category") or "").strip()
        if not major or not middle:
            return None
        minor_raw = classification.get("minor_category")
        minor = (minor_raw or "").strip() or None
        situation_tags = classification_payload.get("situation_tags", [])
        normalized_tags = [str(tag).strip() for tag in situation_tags if isinstance(tag, str)]
        insufficiencies_present = self._has_insufficiencies(result)
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
            insufficiencies_present=insufficiencies_present,
        )

    async def _call_character_reward_api(
        self, reward_request: CharacterRewardRequest
    ) -> CharacterRewardResponse | None:
        headers = {}
        # Istio sidecar handles mTLS authentication; no application-level token needed.
        # if self.settings.character_api_token:
        #     headers["Authorization"] = f"Bearer {self.settings.character_api_token}"
        timeout = httpx.Timeout(self.settings.character_api_timeout_seconds)
        payload = reward_request.model_dump(mode="json")
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._reward_endpoint,
                    json=payload,
                    headers=headers or None,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Character reward API call failed: %s", exc)
            return None

        try:
            data = response.json()
            return CharacterRewardResponse(**data)
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid character reward payload: %s", exc)
            return None

    def _build_reward_endpoint(self) -> str:
        base = self.settings.character_api_base_url.rstrip("/")
        path = self.settings.character_reward_endpoint
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

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
