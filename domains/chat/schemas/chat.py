from typing import Optional

from pydantic import BaseModel, HttpUrl


class ChatMessageRequest(BaseModel):
    message: str
    temperature: float = 0.2
    image_url: Optional[HttpUrl] = None


class ChatMessageResponse(BaseModel):
    user_answer: str
