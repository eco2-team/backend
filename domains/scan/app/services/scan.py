from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4

from app.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)
from domains._shared.schemas.waste import WasteClassificationResult
from domains._shared.waste_pipeline import PipelineError, process_waste_classification
from domains._shared.waste_pipeline.utils import ITEM_CLASS_PATH, load_yaml

DEFAULT_SCAN_PROMPT = "이 폐기물을 어떻게 분리배출해야 하나요?"
_TASK_STORE: Dict[str, ScanTask] = {}


class ScanService:
    _category_cache: List[ScanCategory] | None = None

    async def classify(self, payload: ClassificationRequest) -> ClassificationResponse:
        image_urls = [str(url) for url in payload.image_urls or []]
        if payload.image_url:
            image_urls.append(str(payload.image_url))

        if not image_urls:
            return ClassificationResponse(
                task_id=str(uuid4()),
                status="failed",
                message="이미지 URL이 필요합니다.",
                error="IMAGE_URL_REQUIRED",
            )

        task_id = str(uuid4())
        try:
            pipeline_payload = await asyncio.to_thread(
                process_waste_classification,
                payload.user_input or DEFAULT_SCAN_PROMPT,
                image_urls,
                save_result=False,
                verbose=False,
            )
        except PipelineError as exc:
            return ClassificationResponse(
                task_id=task_id,
                status="failed",
                message="분류 파이프라인 처리에 실패했습니다.",
                error=str(exc),
            )

        pipeline_result = WasteClassificationResult(**pipeline_payload)
        classification = pipeline_result.classification_result.get("classification", {})
        category = classification.get("major_category")
        completed_at = datetime.now(timezone.utc)

        task = ScanTask(
            task_id=task_id,
            status="completed",
            category=category,
            confidence=None,
            completed_at=completed_at,
            pipeline_result=pipeline_result,
        )
        _TASK_STORE[task_id] = task

        return ClassificationResponse(
            task_id=task_id,
            status="completed",
            message="classification completed",
            pipeline_result=pipeline_result,
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
