"""Recyclable Price Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출 + progress notify (UX).
정책/흐름은 SearchRecyclablePriceCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): SearchRecyclablePriceCommand - 정책/흐름
- Service: RecyclablePriceService - 순수 비즈니스 로직

Function Calling:
- LLM이 사용자 메시지에서 재활용품 정보를 동적으로 추출
- 품목 타입(material), 세부 종류(detail_type) 자동 파싱
- Heuristic 대신 LLM 기반 파라미터 결정

사용 시나리오:
1. 재활용품 시세 문의 (예: "캔 한 개 얼마예요?")
2. 카테고리별 시세 조회 (예: "플라스틱 시세 알려줘")
3. 전체 시세 조회

Flow:
    Router → recyclable_price (Function Calling) → API 실행 → Answer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chat_worker.application.commands.search_recyclable_price_command import (
    SearchRecyclablePriceCommand,
    SearchRecyclablePriceInput,
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
    from chat_worker.application.ports.llm import LLMClientPort
    from chat_worker.application.ports.recyclable_price_client import (
        RecyclablePriceClientPort,
    )

logger = logging.getLogger(__name__)

# Function Definition for OpenAI Function Calling
RECYCLABLE_PRICE_FUNCTION = {
    "name": "get_recyclable_price",
    "description": "재활용품의 현재 시세를 조회합니다. 고물상/고철상 판매 가격 정보.",
    "parameters": {
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "enum": ["paper", "plastic", "metal", "glass"],
                "description": "재활용 품목. paper=종이류, plastic=플라스틱, metal=고철, glass=유리병",
            },
            "detail_type": {
                "type": "string",
                "description": "세부 종류 (예: paper일 때 '신문지', '박스', '책')",
            },
        },
        "required": ["material"],
    },
}


def create_recyclable_price_node(
    price_client: "RecyclablePriceClientPort",
    event_publisher: "ProgressNotifierPort",
    llm: "LLMClientPort",
):
    """재활용자원 시세 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - LLM Function Calling으로 파라미터 추출
    - Command(UseCase) 호출
    - output → state 변환
    - progress notify (UX)

    Args:
        price_client: 재활용자원 가격 클라이언트
        event_publisher: 이벤트 발행기
        llm: LLM 클라이언트 (Function Calling용)

    Returns:
        recyclable_price_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    command = SearchRecyclablePriceCommand(price_client=price_client)

    async def _recyclable_price_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. LLM Function Calling으로 파라미터 추출
        3. Command 호출 (정책/흐름 위임)
        4. output → state 변환
        5. progress notify (UX)

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")
        message = state.get("message", "")

        # Progress: 시작 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="recyclable_price",
            status="started",
            progress=45,
            message="재활용자원 시세 조회 중",
        )

        # 1. LLM Function Calling으로 파라미터 추출
        system_prompt = """사용자의 메시지에서 재활용품 시세 조회에 필요한 정보를 추출하세요.

지침:
- 재활용품의 종류를 파악하여 material에 매핑 (paper, plastic, metal, glass)
- 구체적인 품목 이름이 있으면 detail_type에 기록
- 예: "신문지" → material: "paper", detail_type: "신문지"
- 예: "페트병" → material: "plastic", detail_type: "페트병"
- 예: "캔" → material: "metal", detail_type: "캔"
- 예: "유리병" → material: "glass", detail_type: "유리병"

품목 매핑:
- 종이류: 신문지, 박스, 책, 종이 → paper
- 플라스틱: 페트병, 비닐, 플라스틱 → plastic
- 고철/금속: 캔, 철, 알루미늄, 구리 → metal
- 유리: 유리병, 병 → glass
"""

        try:
            func_name, func_args = await llm.generate_function_call(
                prompt=message,
                functions=[RECYCLABLE_PRICE_FUNCTION],
                system_prompt=system_prompt,
                function_call={"name": "get_recyclable_price"},  # 강제 호출
            )

            if not func_args:
                # Function call 실패 → fallback: message 그대로 사용
                logger.warning(
                    "Function call failed, using fallback",
                    extra={"job_id": job_id, "user_message": message},
                )
                func_args = {}

        except Exception as e:
            # LLM 호출 실패 → fallback
            logger.error(
                f"Function calling error: {e}",
                extra={"job_id": job_id, "user_message": message},
            )
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="recyclable_price",
                status="failed",
                result={"error": "파라미터 추출 실패"},
            )
            return {
                "recyclable_price_context": create_error_context(
                    producer="recyclable_price",
                    job_id=job_id,
                    error=f"재활용품 정보를 추출할 수 없습니다: {str(e)}",
                ),
            }

        # 2. Function call 결과 → input DTO 변환
        # material과 detail_type을 사용하여 item_name 생성
        material = func_args.get("material")
        detail_type = func_args.get("detail_type")

        # item_name: detail_type 우선, 없으면 material, 둘 다 없으면 message
        item_name = detail_type or material or message

        input_dto = SearchRecyclablePriceInput(
            job_id=job_id,
            item_name=item_name,
            category=material,  # material을 category로 사용
            region=state.get("recyclable_region"),
            message=message,
        )

        # 3. Command 실행 (정책/흐름은 Command에서)
        output = await command.execute(input_dto)

        # 4. output → state 변환
        if not output.success:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="recyclable_price",
                status="failed",
                result={"error": output.error_message},
            )
            return {
                "recyclable_price_context": create_error_context(
                    producer="recyclable_price",
                    job_id=job_id,
                    error=output.error_message or "재활용자원 시세 조회 실패",
                ),
            }

        # Progress: 완료 (UX)
        context = output.price_context or {}
        found = context.get("found", False)
        count = context.get("count", 0)

        result_message = "재활용자원 시세 조회 완료"
        if found:
            result_message = f"{count}개 품목 시세 조회 완료"
        elif context.get("type") == "guide":
            result_message = "품목 정보 필요"

        await event_publisher.notify_stage(
            task_id=job_id,
            stage="recyclable_price",
            status="completed",
            progress=55,
            result={
                "found": found,
                "count": count,
            },
            message=result_message,
        )

        return {
            "recyclable_price_context": create_context(
                data=output.price_context or {},
                producer="recyclable_price",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def recyclable_price_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨).

        NodeExecutor가 다음을 처리:
        - Circuit Breaker 확인
        - Timeout 적용 (10000ms)
        - Retry (2회)
        - FAIL_FALLBACK 처리 (실패 시 대체 안내)
        """
        return await executor.execute(
            node_name="recyclable_price",
            node_func=_recyclable_price_node_inner,
            state=state,
        )

    return recyclable_price_node


__all__ = ["create_recyclable_price_node"]
