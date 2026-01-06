"""Scan API Controller.

메인 API 엔드포인트:
- POST /scan: 비동기 분류 작업 제출
- GET /scan/result/{job_id}: 결과 조회
- GET /scan/categories: 카테고리 목록
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from scan.application.classify.commands import (
    SubmitClassificationRequest,
)
from scan.application.result.queries.get_result import (
    ProcessingResponse,
)
from scan.setup.config import get_settings
from scan.setup.dependencies import (
    GetCategoriesQueryDep,
    GetResultQueryDep,
    SubmitCommandDep,
)

router = APIRouter(prefix="/scan", tags=["scan"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class ClassificationRequest(BaseModel):
    """분류 요청 스키마."""

    image_url: HttpUrl | None = Field(
        default=None,
        description="분석할 이미지 URL",
    )
    user_input: str | None = Field(
        default=None,
        description="사용자 질문/설명",
    )
    model: str | None = Field(
        default=None,
        description="LLM 모델명 (미지정 시 gpt-5.2)",
        examples=["gpt-5.2", "gpt-5.1", "gemini-2.5-flash"],
    )


class ScanSubmitResponse(BaseModel):
    """분류 제출 응답 스키마."""

    job_id: str = Field(description="작업 ID (UUID)")
    stream_url: str = Field(description="SSE 스트리밍 URL")
    result_url: str = Field(description="결과 조회 URL")
    status: str = Field(default="queued", description="현재 상태")


class ScanProcessingResponse(BaseModel):
    """처리 중 응답 스키마 (202 Accepted)."""

    status: str = Field(default="processing")
    message: str = Field(default="결과 준비 중입니다.")
    current_stage: str | None = None
    progress: int | None = None


class ScanCategory(BaseModel):
    """카테고리 스키마."""

    id: int
    name: str
    display_name: str
    instructions: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# User Authentication (Ext-Authz 연동)
# ─────────────────────────────────────────────────────────────────────────────


class User(BaseModel):
    """인증된 사용자 모델."""

    user_id: str
    role: str | None = None


def get_current_user(
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
) -> User:
    """Ext-Authz에서 주입된 사용자 정보 추출.

    Istio Ingress Gateway의 Ext-Authz가 JWT를 검증한 후
    X-User-ID, X-User-Role 헤더를 주입합니다.

    Args:
        x_user_id: Ext-Authz에서 주입된 사용자 ID
        x_user_role: Ext-Authz에서 주입된 사용자 역할 (optional)

    Returns:
        User: 인증된 사용자 정보

    Raises:
        HTTPException: X-User-ID 헤더가 없는 경우 (401)
    """
    if not x_user_id:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: X-User-ID header is required",
        )
    return User(user_id=x_user_id, role=x_user_role)


CurrentUser = Annotated[User, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ScanSubmitResponse,
    summary="Submit waste image for async classification",
)
async def submit_scan(
    payload: ClassificationRequest,
    user: CurrentUser,
    command: SubmitCommandDep,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> ScanSubmitResponse:
    """이미지 분류 작업을 비동기로 제출합니다.

    클라이언트 흐름:
    1. 이 엔드포인트 호출 → job_id, stream_url, result_url 수신
    2. stream_url로 SSE 연결 → 실시간 진행상황 수신
    3. 완료 후 result_url로 최종 결과 조회
    """
    image_url = str(payload.image_url) if payload.image_url else None
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    # 모델 검증
    settings = get_settings()
    model = payload.model or settings.llm_default_model

    if not settings.validate_model(model):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_model",
                "message": f"Unsupported model: '{model}'",
                "supported_models": settings.get_all_supported_models(),
            },
        )

    request = SubmitClassificationRequest(
        user_id=user.user_id,
        image_url=image_url,
        user_input=payload.user_input,
        idempotency_key=x_idempotency_key,
        model=model,
    )

    response = await command.execute(request)

    return ScanSubmitResponse(
        job_id=response.job_id,
        stream_url=response.stream_url,
        result_url=response.result_url,
        status=response.status,
    )


@router.get(
    "/{job_id}/result",
    summary="Get scan result by job_id",
    responses={
        200: {"description": "결과 반환"},
        202: {"model": ScanProcessingResponse, "description": "처리 중"},
        404: {"description": "작업을 찾을 수 없음"},
    },
)
async def get_result(
    job_id: str,
    query: GetResultQueryDep,
) -> JSONResponse:
    """작업 ID로 분류 결과를 조회합니다.

    Returns:
        200: 결과 반환
        202: 아직 처리 중 (Retry-After: 2초)
        404: job_id에 해당하는 작업 없음
    """
    result = await query.execute(job_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Result not found for job_id: {job_id}",
        )

    if isinstance(result, ProcessingResponse):
        return JSONResponse(
            status_code=202,
            content={
                "status": result.status,
                "message": result.message,
                "current_stage": result.current_stage,
                "progress": result.progress,
            },
            headers={"Retry-After": "2"},
        )

    # ResultResponse
    return JSONResponse(
        status_code=200,
        content={
            "task_id": result.task_id,
            "status": result.status,
            "message": result.message,
            "pipeline_result": result.pipeline_result,
            "reward": result.reward,
            "error": result.error,
        },
    )


@router.get(
    "/categories",
    response_model=list[ScanCategory],
    summary="Supported waste categories",
)
def get_categories(
    query: GetCategoriesQueryDep,
) -> list[ScanCategory]:
    """지원하는 폐기물 카테고리 목록을 반환합니다."""
    categories = query.execute()
    return [
        ScanCategory(
            id=cat.id,
            name=cat.name,
            display_name=cat.display_name,
            instructions=cat.instructions,
        )
        for cat in categories
    ]
