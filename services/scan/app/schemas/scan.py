from datetime import datetime
from typing import List

from pydantic import BaseModel, HttpUrl


class ClassificationRequest(BaseModel):
    image_url: HttpUrl


class ClassificationResponse(BaseModel):
    task_id: str
    status: str
    message: str


class ScanTask(BaseModel):
    task_id: str
    status: str
    category: str
    confidence: float
    completed_at: datetime


class ScanCategory(BaseModel):
    id: int
    name: str
    display_name: str
    instructions: List[str]
