from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid

app = FastAPI(
    title="Chat LLM API",
    description="LLM 채팅 서비스 - 분리수거 질의응답",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic 모델
class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = datetime.now()


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    message: str
    suggestions: List[str] = []


class ChatSession(BaseModel):
    session_id: str
    messages: List[Message]
    created_at: datetime
    updated_at: datetime


class Feedback(BaseModel):
    session_id: str
    message_index: int
    rating: int  # 1-5
    comment: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "healthy", "service": "chat-llm-api"}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "chat-llm-api"}


@app.post("/api/v1/chat/messages", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """메시지 전송 및 LLM 응답"""
    # TODO: Redis에서 대화 히스토리 조회
    # TODO: OpenAI API 호출 (GPT-4o mini)
    # TODO: 응답 생성 후 Redis에 저장

    session_id = request.session_id or str(uuid.uuid4())

    # Dummy response
    return {
        "session_id": session_id,
        "message": "페트병은 세척 후 압착하여 배출하시면 됩니다. 라벨과 뚜껑은 분리해주세요.",
        "suggestions": [
            "플라스틱 용기는 어떻게 버려요?",
            "유리병 배출 방법이 궁금해요",
            "스티로폼은 재활용되나요?",
        ],
    }


@app.get("/api/v1/chat/sessions/{session_id}", response_model=ChatSession)
async def get_session(session_id: str):
    """세션 조회"""
    # TODO: Redis에서 세션 조회
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": "user",
                "content": "페트병은 어떻게 버려요?",
                "timestamp": datetime.now(),
            },
            {
                "role": "assistant",
                "content": "페트병은 세척 후 압착하여 배출하시면 됩니다.",
                "timestamp": datetime.now(),
            },
        ],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }


@app.delete("/api/v1/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """세션 삭제"""
    # TODO: Redis에서 세션 삭제
    return {"message": f"Session {session_id} deleted"}


@app.get("/api/v1/chat/suggestions")
async def get_suggestions():
    """추천 질문 목록"""
    return {
        "suggestions": [
            "페트병은 어떻게 버려요?",
            "종이팩과 종이는 구분해서 버려야 하나요?",
            "일회용 플라스틱 용기는 재활용되나요?",
            "스티로폼은 어떻게 배출하나요?",
            "음식물 쓰레기는 어디까지 버릴 수 있나요?",
        ]
    }


@app.post("/api/v1/chat/feedback")
async def submit_feedback(feedback: Feedback):
    """피드백 제출"""
    # TODO: DB에 피드백 저장
    # TODO: LLM 성능 개선을 위한 데이터로 활용
    return {"message": "Feedback submitted successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
