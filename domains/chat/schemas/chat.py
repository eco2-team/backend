from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl

from domains._shared.schemas.waste import WasteClassificationResult


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    temperature: float = 0.2
    history: Optional[List[ChatMessage]] = None
    image_urls: Optional[List[HttpUrl]] = None


class ChatMessageResponse(BaseModel):
    session_id: str
    message: str
    suggestions: List[str]
    model: str
    latency_ms: Optional[int] = None
    pipeline_result: Optional[WasteClassificationResult] = None


class ChatSession(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    created_at: datetime
    updated_at: datetime
    model: str = "gpt-4o-mini"


class ChatFeedback(BaseModel):
    session_id: str
    rating: int
    comment: Optional[str] = None
