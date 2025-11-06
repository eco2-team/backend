from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Userinfo API", description="사용자 정보 관리 서비스", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic 모델
class UserProfile(BaseModel):
    id: int
    email: str
    username: str
    avatar_url: Optional[str] = None
    points: int = 0
    level: int = 1
    created_at: datetime


class UserUpdate(BaseModel):
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class Activity(BaseModel):
    id: int
    user_id: int
    action: str
    points_earned: int
    timestamp: datetime


@app.get("/health")
def health():
    return {"status": "healthy", "service": "userinfo-api"}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "userinfo-api"}


@app.get("/api/v1/users/{user_id}", response_model=UserProfile)
async def get_user(user_id: int = Path(..., gt=0)):
    """사용자 프로필 조회"""
    # TODO: DB에서 사용자 조회
    return {
        "id": user_id,
        "email": "user@example.com",
        "username": "testuser",
        "avatar_url": "https://example.com/avatar.jpg",
        "points": 1200,
        "level": 3,
        "created_at": datetime.now(),
    }


@app.patch("/api/v1/users/{user_id}", response_model=UserProfile)
async def update_user(user_id: int, user_update: UserUpdate):
    """사용자 프로필 수정"""
    # TODO: DB 업데이트 로직
    return {
        "id": user_id,
        "email": "user@example.com",
        "username": user_update.username or "testuser",
        "avatar_url": user_update.avatar_url,
        "points": 1200,
        "level": 3,
        "created_at": datetime.now(),
    }


@app.get("/api/v1/users/{user_id}/points")
async def get_user_points(user_id: int):
    """사용자 포인트 조회"""
    # TODO: 포인트 조회 로직
    return {
        "user_id": user_id,
        "total_points": 1200,
        "available_points": 1200,
        "used_points": 0,
    }


@app.get("/api/v1/users/{user_id}/history", response_model=List[Activity])
async def get_user_history(
    user_id: int, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)
):
    """사용자 활동 히스토리"""
    # TODO: DB에서 히스토리 조회
    return [
        {
            "id": 1,
            "user_id": user_id,
            "action": "waste_scan",
            "points_earned": 10,
            "timestamp": datetime.now(),
        }
    ]


@app.delete("/api/v1/users/{user_id}")
async def delete_user(user_id: int):
    """계정 삭제"""
    # TODO: 계정 삭제 로직 (soft delete)
    return {"message": f"User {user_id} deleted successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
