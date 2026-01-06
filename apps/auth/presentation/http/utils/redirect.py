"""Frontend Redirect Utilities.

OAuth 콜백 후 프론트엔드로 리다이렉트하기 위한 유틸리티 함수들입니다.

기존 domains/auth/presentation/http/controllers/auth.py에서 이전.
"""

from typing import Optional
from urllib.parse import urlparse, urlunparse

from fastapi import Request
from fastapi.responses import RedirectResponse

# 프론트엔드 오리진 헤더 키
FRONTEND_ORIGIN_HEADER = "x-frontend-origin"

# 기본 포트 (생략 가능)
_DEFAULT_PORTS = {"https": "443", "http": "80"}


def _first_value(header: Optional[str]) -> Optional[str]:
    """쉼표로 구분된 헤더에서 첫 번째 값 추출.

    X-Forwarded-* 헤더는 프록시 체인에서 쉼표로 구분될 수 있음.
    """
    return header.split(",")[0].strip() if header else None


def _resolve_host(request: Request) -> Optional[str]:
    """요청에서 호스트 결정.

    우선순위:
    1. X-Forwarded-Host 헤더 (프록시/로드밸런서)
    2. Host 헤더
    3. URL에서 추출
    """
    forwarded = _first_value(request.headers.get("x-forwarded-host"))
    host_header = _first_value(request.headers.get("host"))
    return forwarded or host_header or request.url.hostname


def _resolve_scheme(request: Request) -> str:
    """요청에서 스킴 결정.

    우선순위:
    1. X-Forwarded-Proto 헤더 (프록시/로드밸런서)
    2. URL에서 추출
    3. 기본값 https
    """
    forwarded = _first_value(request.headers.get("x-forwarded-proto"))
    return forwarded or request.url.scheme or "https"


def get_request_origin(request: Request) -> Optional[str]:
    """요청에서 Origin 추출.

    프록시 헤더 (X-Forwarded-*) 를 고려하여 원본 요청의 Origin을 결정합니다.

    Returns:
        "https://example.com" 형태의 Origin 문자열, 또는 None
    """
    host = _resolve_host(request)
    if not host:
        return None

    scheme = _resolve_scheme(request)

    # 포트 처리: 기본 포트가 아닌 경우에만 포함
    if ":" not in host:
        port = _first_value(request.headers.get("x-forwarded-port"))
        if not port and request.url.port:
            port = str(request.url.port)
        if port and port != _DEFAULT_PORTS.get(scheme.lower()):
            host = f"{host}:{port}"

    return f"{scheme}://{host}"


def build_frontend_success_url(frontend_url: str) -> str:
    """프론트엔드 성공 리다이렉트 URL 생성.

    Args:
        frontend_url: 기본 프론트엔드 URL (예: https://frontend.example.com)

    Returns:
        홈 페이지 URL (예: https://frontend.example.com/#/home)
    """
    sanitized = frontend_url.rstrip("/")
    return f"{sanitized}/#/home"


def build_frontend_redirect_url(
    request: Request, fallback_url: str, frontend_origin: str | None
) -> str:
    """프론트엔드 리다이렉트 URL 생성.

    프론트엔드 오리진과 fallback URL을 결합하여 최종 리다이렉트 URL을 생성합니다.

    예시:
        - frontend_origin: "https://custom.frontend.com"
        - fallback_url: "https://default.frontend.com/login?error=oauth_failed"
        - 결과: "https://custom.frontend.com/login?error=oauth_failed"

    Args:
        request: FastAPI Request 객체
        fallback_url: 기본 리다이렉트 URL
        frontend_origin: 프론트엔드 오리진 (X-Frontend-Origin 헤더 또는 state에서)

    Returns:
        최종 리다이렉트 URL
    """
    # frontend_origin이 명시적으로 지정된 경우에만 origin을 변경
    # OAuth 콜백에서 헤더가 없으면 fallback_url 그대로 사용
    if not frontend_origin:
        return fallback_url

    parsed_origin = urlparse(frontend_origin)
    parsed_fallback = urlparse(fallback_url)

    scheme = parsed_origin.scheme or parsed_fallback.scheme
    netloc = parsed_origin.netloc or parsed_fallback.netloc
    if not scheme or not netloc:
        return fallback_url

    path = parsed_fallback.path or "/"

    return urlunparse(
        (
            scheme,
            netloc,
            path,
            parsed_fallback.params,
            parsed_fallback.query,
            parsed_fallback.fragment,
        )
    )


def build_frontend_redirect_response(
    request: Request, fallback_url: str, frontend_origin: str | None
) -> RedirectResponse:
    """프론트엔드 리다이렉트 Response 생성.

    Args:
        request: FastAPI Request 객체
        fallback_url: 기본 리다이렉트 URL
        frontend_origin: 프론트엔드 오리진

    Returns:
        RedirectResponse 객체
    """
    redirect_url = build_frontend_redirect_url(request, fallback_url, frontend_origin)
    return RedirectResponse(url=redirect_url)
