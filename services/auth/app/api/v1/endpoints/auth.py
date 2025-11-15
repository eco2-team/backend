from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth import Token, User, UserCreate, UserLogin
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register_user(
    payload: UserCreate,
    service: Annotated[AuthService, Depends()],
):
    return await service.register_user(payload)


@router.post("/login", response_model=Token, summary="Issue JWT access token")
async def login(
    credentials: UserLogin,
    service: Annotated[AuthService, Depends()],
):
    token = await service.login(credentials)
    if token.expires_in <= 0:
        raise HTTPException(status_code=400, detail="Invalid token expiry")
    return token


@router.post("/logout", summary="Invalidate current token")
async def logout(
    token: Annotated[str, Depends(AuthService.token_dependency)],
    service: Annotated[AuthService, Depends()],
):
    await service.logout(token)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=User, summary="Fetch current user profile")
async def get_current_user(
    token: Annotated[str, Depends(AuthService.token_dependency)],
    service: Annotated[AuthService, Depends()],
):
    return await service.get_current_user(token)


@router.post("/refresh", response_model=Token, summary="Refresh access token")
async def refresh_token(
    token: Annotated[str, Depends(AuthService.token_dependency)],
    service: Annotated[AuthService, Depends()],
):
    refreshed = await service.refresh_token(token)
    if refreshed.expires_in <= 0:
        raise HTTPException(status_code=400, detail="Unable to refresh token")
    return refreshed


@router.get(
    "/sessions",
    summary="List active sessions (dummy data)",
    response_model=list[Token],
)
async def list_sessions(service: Annotated[AuthService, Depends()]):
    now = datetime.utcnow()
    return [
        Token(
            access_token=f"session-{idx}",
            token_type="bearer",
            expires_in=int((now + timedelta(minutes=30)).timestamp()),
        )
        for idx in range(1, 3)
    ]
