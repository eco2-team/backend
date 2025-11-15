from datetime import datetime
from uuid import uuid4

from app.schemas.scan import (
    ClassificationRequest,
    ClassificationResponse,
    ScanCategory,
    ScanTask,
)


class ScanService:
    async def classify(self, payload: ClassificationRequest) -> ClassificationResponse:
        task_id = str(uuid4())
        return ClassificationResponse(
            task_id=task_id,
            status="pending",
            message=f"classification queued for {payload.image_url}",
        )

    async def task(self, task_id: str) -> ScanTask:
        return ScanTask(
            task_id=task_id,
            status="completed",
            category="plastic",
            confidence=0.94,
            completed_at=datetime.utcnow(),
        )

    async def categories(self) -> list[ScanCategory]:
        return [
            ScanCategory(
                id=1,
                name="plastic",
                display_name="플라스틱",
                instructions=["세척 후 압착", "뚜껑과 라벨 분리"],
            ),
            ScanCategory(
                id=2,
                name="paper",
                display_name="종이",
                instructions=["스테이플러 제거", "도톰한 종이는 묶어서 배출"],
            ),
        ]

    async def metrics(self) -> dict:
        return {
            "queued_tasks": 5,
            "avg_processing_ms": 820,
            "successful_classifications": 320,
        }
