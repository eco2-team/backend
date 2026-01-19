"""Image Generation Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GenerateImageCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GenerateImageCommand - 정책/흐름
- Port: ImageGeneratorPort - Responses API 호출

아키텍처 의사결정:
- 기존 Chat Completions 파이프라인 유지
- 이미지 생성 서브에이전트에서만 Responses API 사용
- multi-intent 라우팅 구조 그대로 활용
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.generate_image_command import (
    GenerateImageCommand,
    GenerateImageInput,
)
from chat_worker.infrastructure.orchestration.langgraph.context_helper import (
    create_context,
    create_error_context,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.image_generator import ImageGeneratorPort

logger = logging.getLogger(__name__)


def create_image_generation_node(
    image_generator: "ImageGeneratorPort",
    event_publisher: "ProgressNotifierPort",
    default_size: str = "1024x1024",
    default_quality: str = "medium",
):
    """Image Generation 노드 생성.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        image_generator: 이미지 생성 클라이언트 (Responses API)
        event_publisher: 이벤트 발행자 (SSE)
        default_size: 기본 이미지 크기 (Config에서 주입)
        default_quality: 기본 이미지 품질 (Config에서 주입)

    Returns:
        LangGraph 노드 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GenerateImageCommand(image_generator=image_generator)

    async def _image_generation_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환
        4. progress notify (UX)

        Args:
            state: 현재 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        # 사용자 메시지를 프롬프트로 사용 (다른 노드와 동일한 패턴)
        query = state.get("message", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="image_generation",
            status="processing",
            progress=50,
            message="이미지 생성 중",
        )

        # 1. state → input DTO 변환 (state에서 override 가능)
        # 캐릭터 참조 이미지가 있으면 추출 (병렬 라우팅으로 character → image_generation)
        character_context = state.get("character_context") or {}
        character_asset = character_context.get("asset") if character_context else None
        reference_bytes = character_asset.get("image_bytes") if character_asset else None

        if reference_bytes:
            logger.info(
                "Using character reference image for generation",
                extra={
                    "job_id": job_id,
                    "character_code": character_asset.get("code") if character_asset else None,
                    "reference_size": len(reference_bytes),
                },
            )

        input_dto = GenerateImageInput(
            job_id=job_id,
            prompt=query,
            size=state.get("image_size") or default_size,
            quality=state.get("image_quality") or default_quality,
            reference_image_bytes=reference_bytes,
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="image_generation",
                status="failed",
                result={"error": output.error_message},
                message="이미지 생성 실패",
            )
            return {
                "image_generation_context": create_error_context(
                    producer="image_generation",
                    job_id=job_id,
                    error=output.error_message or "이미지 생성 실패",
                ),
            }

        # Progress: 완료 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="image_generation",
            status="completed",
            progress=80,
            result={"image_url": output.image_url},
            message="이미지 생성 완료",
        )

        return {
            "image_generation_context": create_context(
                data={
                    "image_url": output.image_url,
                    "description": output.description,
                    "revised_prompt": output.revised_prompt,
                    "used_reference": reference_bytes is not None,
                    "character_code": character_asset.get("code") if character_asset else None,
                },
                producer="image_generation",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def image_generation_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (30000ms)
        - Retry (1회)
        - FAIL_OPEN 처리 (실패해도 진행)
        """
        return await executor.execute(
            node_name="image_generation",
            node_func=_image_generation_node_inner,
            state=state,
        )

    return image_generation_node
