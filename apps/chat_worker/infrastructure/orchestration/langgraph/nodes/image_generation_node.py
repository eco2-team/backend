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
        query = state.get("query", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="image_generation",
            status="processing",
            progress=50,
            message="이미지 생성 중",
        )

        # 1. state → input DTO 변환 (state에서 override 가능)
        input_dto = GenerateImageInput(
            job_id=job_id,
            prompt=query,
            size=state.get("image_size") or default_size,
            quality=state.get("image_quality") or default_quality,
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
                **state,
                "generated_image_url": None,
                "image_description": None,
                "image_generation_error": output.error_message,
                # answer는 answer_node에서 생성하도록 컨텍스트 전달
                "image_generation_context": {
                    "success": False,
                    "error": output.error_message,
                },
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
            **state,
            "generated_image_url": output.image_url,
            "image_description": output.description,
            # answer_node에서 사용할 컨텍스트
            "image_generation_context": {
                "success": True,
                "image_url": output.image_url,
                "description": output.description,
                "revised_prompt": output.revised_prompt,
            },
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
