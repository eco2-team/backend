from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import os

# FastAPI 앱
app = FastAPI(
    title="Auth API", description="인증/인가 서비스 - JWT 기반 인증", version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 스키마
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# Pydantic 모델
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    username: str


class User(BaseModel):
    id: int
    email: str
    username: str
    created_at: datetime


# Health check
@app.get("/health")
def health():
    return {"status": "healthy", "service": "auth-api"}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "auth-api"}


# API v1
@app.post(
    "/api/v1/auth/register", response_model=User, status_code=status.HTTP_201_CREATED
)
async def register(user: UserRegister):
    """회원가입"""
    # TODO: 실제 DB 저장 로직
    return {
        "id": 1,
        "email": user.email,
        "username": user.username,
        "created_at": datetime.now(),
    }


@app.post("/api/v1/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """로그인 - JWT 토큰 발급"""
    # TODO: 실제 인증 로직
    # TODO: JWT 토큰 생성
    return {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "expires_in": 3600,
    }


@app.post("/api/v1/auth/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    """로그아웃 - 토큰 무효화"""
    # TODO: Redis에 블랙리스트 추가
    return {"message": "Successfully logged out"}


@app.get("/api/v1/auth/me", response_model=User)
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """현재 로그인한 사용자 정보"""
    # TODO: JWT 토큰 검증 및 사용자 조회
    return {
        "id": 1,
        "email": "user@example.com",
        "username": "testuser",
        "created_at": datetime.now(),
    }


@app.post("/api/v1/auth/refresh", response_model=Token)
async def refresh_token(token: str = Depends(oauth2_scheme)):
    """토큰 갱신"""
    # TODO: Refresh token 검증 및 새 토큰 발급
    return {
        "access_token": "new_token_here",
        "token_type": "bearer",
        "expires_in": 3600,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
