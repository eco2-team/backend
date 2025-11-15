from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from app.schemas.auth import Token, User, UserCreate, UserLogin


class AuthService:
    """Lightweight placeholder service that mimics auth workflows."""

    async def register_user(self, payload: UserCreate) -> User:
        return User(
            id=1,
            email=payload.email,
            username=payload.username,
            created_at=datetime.utcnow(),
        )

    async def login(self, credentials: UserLogin) -> Token:
        return self._issue_token(suffix=credentials.email)

    async def logout(self, token: str) -> None:
        # Placeholder: in real implementation, push token to blacklist
        _ = token

    async def get_current_user(self, token: str) -> User:
        return User(
            id=1,
            email="user@example.com",
            username="demo-user",
            created_at=datetime.utcnow() - timedelta(days=30),
        )

    async def refresh_token(self, token: str) -> Token:
        _ = token
        return self._issue_token(suffix="refresh")

    async def get_metrics(self) -> dict:
        return {
            "active_sessions": 3,
            "login_success_rate": 0.98,
            "token_issued_last_hour": 42,
        }

    @staticmethod
    async def token_dependency(token: Optional[str] = None) -> str:
        if not token:
            # In FastAPI this dependency would read from Authorization header,
            # but for placeholder purposes we just fall back to demo token.
            return "demo-token"
        return token

    def _issue_token(self, suffix: str) -> Token:
        expires = int((datetime.utcnow() + timedelta(hours=1)).timestamp())
        return Token(
            access_token=f"{uuid4()}::{suffix}",
            token_type="bearer",
            expires_in=expires,
        )
