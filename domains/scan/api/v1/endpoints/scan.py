"""Scan API endpoints."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from domains.scan.api.dependencies import CurrentUser, ScanServiceDep
from domains.scan.schemas.scan import (
    AsyncClassifyResponse,
    AsyncTaskState,
    AsyncTaskStatus,
    ClassificationRequest,
    ClassificationResponse,
    PartialClassificationResult,
    ScanCategory,
    ScanTask,
)

router = APIRouter(prefix="/scan", tags=["scan"])


# ============================================================
# 기존 동기 API (호환성 유지)
# ============================================================


@router.post(
    "/classify",
    response_model=ClassificationResponse,
    summary="Submit waste image for classification (sync)",
)
async def classify(
    payload: ClassificationRequest,
    user: CurrentUser,
    service: ScanServiceDep,
) -> ClassificationResponse:
    """이미지를 분석하여 폐기물을 분류합니다 (동기 버전)."""
    return await service.classify(payload, user.user_id)


@router.get(
    "/task/{task_id}",
    response_model=ScanTask,
    summary="Fetch classification task result (legacy)",
)
async def task(task_id: str, service: ScanServiceDep) -> ScanTask:
    """태스크 ID로 분류 결과를 조회합니다 (기존 DB 기반)."""
    try:
        return await service.task(task_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task {task_id} not found",
        )


@router.get(
    "/categories",
    response_model=list[ScanCategory],
    summary="Supported waste categories",
)
async def categories(service: ScanServiceDep) -> list[ScanCategory]:
    """지원하는 폐기물 카테고리 목록을 반환합니다."""
    return await service.categories()


# ============================================================
# 비동기 API (Celery + RabbitMQ)
# ============================================================


@router.post(
    "/classify/async",
    response_model=AsyncClassifyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit waste image for async classification",
    description="""
    비동기 분류 요청을 제출합니다.

    응답으로 task_id를 받고, GET /task/{task_id}/status로 진행 상황을 폴링하세요.

    **프론트엔드 연동**:
    1. POST /classify/async → task_id 수신 (202 Accepted)
    2. GET /task/{task_id}/status → 폴링 (0.5초 간격 권장)
    3. status가 completed/failed가 될 때까지 반복
    """,
)
async def classify_async(
    payload: ClassificationRequest,
    user: CurrentUser,
) -> AsyncClassifyResponse:
    """비동기 분류 요청을 제출합니다 (즉시 응답)."""
    from domains._shared.taskqueue.state import TaskState, TaskStatus, TaskStep, get_state_manager
    from domains.scan.tasks.classification import run_classification_pipeline

    # 입력 검증
    if not payload.image_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="image_url is required",
        )

    # Task ID 생성
    task_id = str(uuid4())
    image_url = str(payload.image_url)
    user_input = payload.user_input or ""

    # Redis에 초기 상태 저장
    state = TaskState(
        task_id=task_id,
        user_id=str(user.user_id),
        status=TaskStatus.QUEUED,
        step=TaskStep.PENDING,
        progress=0,
        image_url=image_url,
    )

    manager = get_state_manager()
    await manager.create(state)

    # Celery Chain 발행 (비동기)
    run_classification_pipeline(task_id, image_url, user_input)

    return AsyncClassifyResponse(
        task_id=task_id,
        status=AsyncTaskStatus.QUEUED,
        message="분류 작업이 큐에 등록되었습니다. GET /task/{task_id}/status로 진행 상황을 확인하세요.",
    )


@router.get(
    "/task/{task_id}/status",
    response_model=AsyncTaskState,
    summary="Fetch async task status",
    description="""
    비동기 태스크의 현재 상태를 조회합니다.

    **응답 필드**:
    - `status`: queued | processing | completed | failed
    - `step`: pending | scan | analyze | answer | complete
    - `progress`: 0-100 (UI 프로그레스 바용)
    - `partial_result`: 단계별 부분 결과 (진행 중에도 표시 가능)
    - `result`: 최종 결과 (completed 시)

    **폴링 권장 간격**: 500ms
    """,
)
async def task_status(task_id: str) -> AsyncTaskState:
    """비동기 태스크의 상태를 조회합니다."""
    from domains._shared.taskqueue.state import get_state_manager

    manager = get_state_manager()
    state = await manager.get(task_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    # TaskState → AsyncTaskState 변환
    partial = None
    if state.partial_result:
        partial = PartialClassificationResult(
            classification=state.partial_result.get("classification"),
            situation_tags=state.partial_result.get("situation_tags"),
        )

    return AsyncTaskState(
        task_id=state.task_id,
        status=AsyncTaskStatus(state.status.value),
        step=state.step.value,
        progress=state.progress,
        partial_result=partial,
        result=state.result,
        error=state.error,
        error_code=state.error_code,
        reward_status=state.reward_status,
        created_at=state.created_at,
        updated_at=state.updated_at,
        metadata=state.metadata,
    )
