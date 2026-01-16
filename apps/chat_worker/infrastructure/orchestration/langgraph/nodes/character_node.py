"""Character Subagent Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 GetCharacterCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GetCharacterCommand - 정책/흐름
- Service: CategoryExtractorService, CharacterService - 순수 비즈니스 로직

Production Architecture:
- NodeExecutor로 Policy 적용 (timeout, retry, circuit breaker)
- character 노드는 FAIL_OPEN (선택적 컨텍스트)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.get_character_command import (
    GetCharacterCommand,
    GetCharacterInput,
)
from chat_worker.infrastructure.orchestration.langgraph.nodes.node_executor import (
    NodeExecutor,
)

if TYPE_CHECKING:
    from chat_worker.application.ports.character_client import CharacterClientPort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.prompt_loader import PromptLoaderPort

logger = logging.getLogger(__name__)


def create_character_subagent_node(
    llm: "LLMClientPort",
    character_client: "CharacterClientPort",
    event_publisher: "ProgressNotifierPort",
    prompt_loader: "PromptLoaderPort",
):
    """Character Subagent 노드 생성.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        llm: LLM 클라이언트 (Command에서 카테고리 추출용)
        character_client: Character gRPC 클라이언트
        event_publisher: 이벤트 발행자 (SSE 진행 상황)
        prompt_loader: 프롬프트 로더

    Returns:
        LangGraph 노드 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = GetCharacterCommand(
        llm=llm,
        character_client=character_client,
        prompt_loader=prompt_loader,
    )

    async def _character_subagent_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. Command 호출 (정책/흐름 위임)
        3. output → state 변환

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="character",
            status="processing",
            progress=50,
            message="캐릭터 정보 조회 중",
        )

        # 1. state → input DTO 변환
        input_dto = GetCharacterInput(
            job_id=job_id,
            message=state.get("message", ""),
        )

        # 2. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 3. output → state 변환
        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="character",
                status="failed",
                result={"error": output.error_message},
                message="캐릭터 정보 조회 실패",
            )
            return {
                **state,
                "character_context": None,
                "subagent_error": output.error_message,
            }

        # Progress: 완료 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="character",
            status="completed",
            progress=55,
            message="캐릭터 정보 조회 완료",
        )

        return {
            **state,
            "character_context": output.character_context,
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def character_subagent(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (3000ms)
        - Retry (1회)
        - FAIL_OPEN 처리 (실패해도 진행)
        """
        return await executor.execute(
            node_name="character",
            node_func=_character_subagent_inner,
            state=state,
        )

    return character_subagent
