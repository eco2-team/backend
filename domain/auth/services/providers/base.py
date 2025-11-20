from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

import httpx

from domain.auth.schemas.oauth import OAuthProfile


class OAuthProviderError(RuntimeError):
    pass


class OAuthProvider(ABC):
    name: str
    supports_pkce: bool = True

    def __init__(
        self, *, client_id: str, client_secret: Optional[str], redirect_uri: Optional[str]
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @property
    def default_scopes(self) -> Iterable[str]:
        return ()

    @abstractmethod
    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: Optional[str],
        scope: Optional[str],
        redirect_uri: Optional[str],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code(
        self,
        *,
        client: httpx.AsyncClient,
        code: str,
        code_verifier: Optional[str],
        redirect_uri: str,
        state: Optional[str],
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def fetch_profile(
        self,
        *,
        client: httpx.AsyncClient,
        tokens: dict,
    ) -> OAuthProfile:
        raise NotImplementedError
