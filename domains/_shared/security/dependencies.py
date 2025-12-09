from __future__ import annotations

from typing import Callable, Optional

from fastapi import Header, HTTPException, status

from .jwt import TokenPayload, TokenType, extract_token_payload


def build_access_token_dependency(
    get_settings: Callable,
    *,
    cookie_alias: str = "s_access",  # 호환성을 위해 인자는 남겨두지만 사용하지 않음
    blacklist_dependency: Optional[type] = None,  # 호환성을 위해 남겨두지만 사용하지 않음
):
    """
    Factory that returns a FastAPI dependency for extracting access-token from Authorization header.

    Auth Offloading:
    - Signature Verification: Handled by Istio RequestAuthentication
    - Blacklist Check: Handled by Istio External Authorization (gRPC to Auth Service)
    - This dependency ONLY extracts payload for business logic usage.
    """

    async def dependency(
        authorization: Optional[str] = Header(default=None),
    ) -> TokenPayload:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header"
            )

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format"
            )

        # Decode without verification (Istio & ExtAuthz handled security)
        payload = extract_token_payload(token)

        if payload.type is not TokenType.ACCESS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token type mismatch"
            )
        return payload

    return dependency
