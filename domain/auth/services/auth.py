from __future__ import annotations

import httpx
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from domain.auth.core.config import Settings, get_settings
from domain.auth.core.security import now_utc
from domain.auth.database.session import get_db_session
from domain.auth.repositories import LoginAuditRepository, UserRepository
from domain.auth.schemas.auth import (
    AuthorizationResponse,
    OAuthAuthorizeParams,
    OAuthLoginRequest,
    User,
)
from domain.auth.services.providers import OAuthProviderError, ProviderRegistry
from domain.auth.services.state_service import OAuthStateStore
from domain.auth.services.token_blacklist import TokenBlacklist
from domain.auth.services.token_service import TokenService, TokenType
from domain.auth.services.user_token_store import UserTokenStore
from domain._shared.security import TokenPayload

ACCESS_COOKIE_NAME = "s_access"
REFRESH_COOKIE_NAME = "s_refresh"
COOKIE_PATH = "/"
COOKIE_SAMESITE = "lax"


class AuthService:
    def __init__(
        self,
        session: AsyncSession = Depends(get_db_session),
        token_service: TokenService = Depends(TokenService),
        state_store: OAuthStateStore = Depends(OAuthStateStore),
        blacklist: TokenBlacklist = Depends(TokenBlacklist),
        token_store: UserTokenStore = Depends(UserTokenStore),
        settings: Settings = Depends(get_settings),
    ):
        self.session = session
        self.token_service = token_service
        self.state_store = state_store
        self.blacklist = blacklist
        self.user_token_store = token_store
        self.settings = settings
        self.providers = ProviderRegistry(settings)
        self.user_repo = UserRepository(session)
        self.login_audit_repo = LoginAuditRepository(session)
        self.http_timeout = 10.0

    async def authorize(
        self, provider_name: str, params: OAuthAuthorizeParams
    ) -> AuthorizationResponse:
        provider = self._get_provider(provider_name)
        redirect_uri = params.redirect_uri or provider.redirect_uri
        if not redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is required"
            )

        state, _, code_challenge, expires_at_ts = await self.state_store.create_state(
            provider=provider.name,
            redirect_uri=str(redirect_uri),
            scope=params.scope,
            device_id=params.device_id,
        )

        authorization_url = provider.build_authorization_url(
            state=state,
            code_challenge=code_challenge if provider.supports_pkce else None,
            scope=params.scope,
            redirect_uri=str(redirect_uri),
        )

        return AuthorizationResponse(
            provider=provider.name,
            state=state,
            authorization_url=authorization_url,
            expires_at=datetime.fromtimestamp(expires_at_ts, tz=timezone.utc),
        )

    async def login_with_provider(
        self,
        provider_name: str,
        payload: OAuthLoginRequest,
        *,
        response: Response,
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> User:
        provider = self._get_provider(provider_name)
        state_data = await self.state_store.consume_state(payload.state)
        if not state_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state"
            )
        if state_data.get("provider") != provider.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="State provider mismatch"
            )

        redirect_uri = (
            payload.redirect_uri or state_data.get("redirect_uri") or provider.redirect_uri
        )
        if not redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri is required"
            )

        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                tokens = await provider.exchange_code(
                    client=client,
                    code=payload.code,
                    code_verifier=state_data.get("code_verifier"),
                    redirect_uri=str(redirect_uri),
                    state=payload.state,
                )
                profile = await provider.fetch_profile(client=client, tokens=tokens)
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Provider API error"
            ) from exc
        except (httpx.HTTPError, OAuthProviderError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        user = await self.user_repo.upsert_from_profile(profile)

        token_pair = self.token_service.issue_pair(user_id=user.id, provider=provider.name)
        access_payload = self.token_service.decode(token_pair.access_token)
        self.token_service.ensure_type(access_payload, TokenType.ACCESS)
        refresh_payload = self.token_service.decode(token_pair.refresh_token)
        self.token_service.ensure_type(refresh_payload, TokenType.REFRESH)

        await self.user_token_store.register(
            user_id=user.id,
            jti=refresh_payload.jti,
            issued_at=refresh_payload.iat,
            expires_at=refresh_payload.exp,
            device_id=state_data.get("device_id"),
            user_agent=user_agent,
        )

        await self.login_audit_repo.add(
            user_id=user.id,
            provider=provider.name,
            jti=access_payload.jti,
            login_ip=ip_address,
            user_agent=user_agent,
        )
        await self.session.commit()

        self._apply_session_cookies(response, token_pair, access_payload, refresh_payload)
        return User.model_validate(user)

    async def refresh_session(
        self,
        refresh_token: Optional[str],
        *,
        response: Response,
    ) -> User:
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
            )

        payload = self.token_service.decode(refresh_token)
        self.token_service.ensure_type(payload, TokenType.REFRESH)

        if await self.blacklist.contains(payload.jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

        if not await self.user_token_store.contains(payload.user_id, payload.jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found"
            )

        metadata = await self.user_token_store.get_metadata(payload.jti)

        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        await self.user_token_store.remove(payload.user_id, payload.jti)
        await self.blacklist.add(payload, reason="token_rotated")

        token_pair = self.token_service.issue_pair(user_id=user.id, provider=payload.provider)
        access_payload = self.token_service.decode(token_pair.access_token)
        self.token_service.ensure_type(access_payload, TokenType.ACCESS)
        refresh_payload = self.token_service.decode(token_pair.refresh_token)
        self.token_service.ensure_type(refresh_payload, TokenType.REFRESH)

        await self.user_token_store.register(
            user_id=user.id,
            jti=refresh_payload.jti,
            issued_at=refresh_payload.iat,
            expires_at=refresh_payload.exp,
            device_id=metadata.device_id if metadata else None,
            user_agent=metadata.user_agent if metadata else None,
        )
        await self.session.commit()

        self._apply_session_cookies(response, token_pair, access_payload, refresh_payload)
        return User.model_validate(user)

    async def logout(
        self,
        *,
        access_token: Optional[str],
        refresh_token: Optional[str],
        response: Response,
    ) -> None:
        if access_token:
            try:
                payload = self.token_service.decode(access_token)
                self.token_service.ensure_type(payload, TokenType.ACCESS)
                await self.blacklist.add(payload, reason="logout")
            except HTTPException:
                pass

        if refresh_token:
            try:
                payload = self.token_service.decode(refresh_token)
                self.token_service.ensure_type(payload, TokenType.REFRESH)
                await self.blacklist.add(payload, reason="logout")
                await self.user_token_store.remove(payload.user_id, payload.jti)
            except HTTPException:
                pass

        await self.session.commit()
        self._clear_session_cookies(response)

    async def get_current_user(self, payload: TokenPayload) -> User:
        user = await self.user_repo.get(payload.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return User.model_validate(user)

    async def get_metrics(self) -> dict:
        return {"providers": list(self.providers.providers.keys())}

    def _get_provider(self, provider: str):
        try:
            return self.providers.get(provider)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    def _apply_session_cookies(
        self,
        response: Response,
        token_pair,
        access_payload: TokenPayload,
        refresh_payload: TokenPayload,
    ) -> None:
        self._set_cookie(response, ACCESS_COOKIE_NAME, token_pair.access_token, access_payload.exp)
        self._set_cookie(
            response, REFRESH_COOKIE_NAME, token_pair.refresh_token, refresh_payload.exp
        )

    def _clear_session_cookies(self, response: Response) -> None:
        response.delete_cookie(ACCESS_COOKIE_NAME, path=COOKIE_PATH)
        response.delete_cookie(REFRESH_COOKIE_NAME, path=COOKIE_PATH)

    def _set_cookie(self, response: Response, name: str, value: str, expires_at: int) -> None:
        max_age = max(expires_at - int(now_utc().timestamp()), 1)
        response.set_cookie(
            key=name,
            value=value,
            max_age=max_age,
            httponly=True,
            secure=True,
            samesite=COOKIE_SAMESITE,
            path=COOKIE_PATH,
        )
