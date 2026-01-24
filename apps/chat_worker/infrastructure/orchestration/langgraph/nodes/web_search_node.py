"""Web Search Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + LLM 도구 호출 + context 저장.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- LLM: generate_with_tools() - 네이티브 웹 검색 (OpenAI/Gemini)

Production Architecture:
- NodeExecutor로 Policy 적용 (timeout, retry, circuit breaker)
- web_search 노드는 FAIL_OPEN (보조 정보, 없어도 답변 가능)

Dual Mode (weather_node 패턴):
1. Standalone: intent="web_search" → 무조건 검색 수행
2. Enrichment: 다른 intent의 보조 → Function Calling으로 필요 여부 판단

Channel Separation:
- 출력 채널: web_search_results
- Reducer: priority_preemptive_reducer
- spread 금지: {"web_search_results": create_context(...)} 형태로 반환

Native Web Search:
- OpenAI: Responses API web_search tool
- Gemini: Google Search Grounding
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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

logger = logging.getLogger(__name__)

# Function Definition for enrichment mode (검색 필요 여부 판단)
WEB_SEARCH_DECISION_FUNCTION = {
    "name": "web_search_decision",
    "description": (
        "사용자 질문에 실시간 웹 검색이 필요한지 판단합니다. "
        "최신 정보, 뉴스, 정책, 규제, 통계 등 LLM 학습 데이터만으로 "
        "정확하게 답할 수 없는 경우 true를 반환합니다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "needs_search": {
                "type": "boolean",
                "description": (
                    "웹 검색이 필요한지 여부. "
                    "최신 정책, 뉴스, 규제 변경, 실시간 데이터가 필요하면 true. "
                    "일반 상식, 고정된 규칙, 시간 무관한 정보면 false."
                ),
            },
            "search_query": {
                "type": "string",
                "description": (
                    "웹 검색에 사용할 최적화된 한국어 검색 쿼리. "
                    "사용자 질문을 검색에 적합한 키워드 형태로 변환."
                ),
            },
        },
        "required": ["needs_search"],
    },
}

# enrichment mode에서 사용하는 시스템 프롬프트
WEB_SEARCH_DECISION_SYSTEM_PROMPT = """당신은 웹 검색 필요 여부를 판단하는 분석기입니다.

사용자의 질문을 분석하여 실시간 웹 검색이 필요한지 판단하세요.

## 검색이 필요한 경우 (needs_search: true)
- 최신 정보가 필요한 질문 (정책 변경, 새 규제, 최근 뉴스)
- 시간에 민감한 데이터 (올해, 최근, 현재 등)
- LLM 학습 데이터로 정확히 답할 수 없는 실시간 정보

## 검색이 불필요한 경우 (needs_search: false)
- 일반적인 분리배출 방법 (고정된 규칙)
- 환경 상식 (탄소중립, 환경 보호)
- 시간에 무관한 고정 정보
- 이미 다른 전문 에이전트가 처리할 정보 (시세, 날씨, 장소)
"""

# Standalone mode에서 사용하는 시스템 프롬프트 (검색 결과 요약용)
WEB_SEARCH_SYSTEM_PROMPT = """당신은 웹 검색 결과를 바탕으로 정확하고 유용한 정보를 제공하는 도우미입니다.

## 규칙
1. 검색 결과를 바탕으로 사실에 기반한 답변을 제공하세요.
2. 출처가 불분명한 정보는 제외하세요.
3. 최신 정보를 우선하여 답변하세요.
4. 답변은 간결하고 핵심적으로 작성하세요.
5. 관련 정보가 없으면 솔직하게 안내하세요.
"""


def create_web_search_node(
    llm: "LLMClientPort",
    event_publisher: "ProgressNotifierPort | None" = None,
):
    """웹 검색 노드 팩토리.

    Dual Mode:
    - Standalone (intent="web_search"): 무조건 검색 수행
    - Enrichment (other intents): Function Calling으로 필요 여부 판단

    Args:
        llm: LLM 클라이언트 (generate_with_tools, generate_function_call 지원)
        event_publisher: 이벤트 발행자 (진행 상황 알림용)

    Returns:
        web_search_node 함수
    """

    async def _execute_web_search(
        message: str,
        job_id: str,
        max_result_chars: int = 50_000,
    ) -> str | None:
        """네이티브 웹 검색 실행.

        Args:
            message: 검색 쿼리
            job_id: 작업 ID
            max_result_chars: 결과 최대 문자 수 (기본 50K chars ≈ 12.5K tokens)
        """
        result_parts: list[str] = []

        try:
            async for chunk in llm.generate_with_tools(
                prompt=message,
                tools=["web_search"],
                system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            ):
                if chunk:
                    result_parts.append(chunk)
        except Exception as e:
            logger.error(
                "Web search execution failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            return None

        result = "".join(result_parts)
        if not result.strip():
            return None

        if len(result) > max_result_chars:
            logger.warning(
                "Web search result truncated",
                extra={
                    "job_id": job_id,
                    "original_chars": len(result),
                    "truncated_to": max_result_chars,
                },
            )
            result = result[:max_result_chars]

        return result

    async def _web_search_node_inner(state: dict[str, Any]) -> dict[str, Any]:
        """실제 노드 로직 (NodeExecutor가 래핑)."""
        job_id = state.get("job_id", "")
        message = state.get("message", "")
        intent = state.get("intent", "general")

        # Standalone mode: intent == "web_search" → 무조건 검색
        is_standalone = intent == "web_search"

        # 1. 진행 상황 알림
        if event_publisher is not None:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="started",
                progress=30,
                message="웹 검색 중...",
            )

        # 2. Enrichment mode: Function Calling으로 필요 여부 판단
        search_query = message
        if not is_standalone:
            try:
                _, func_args = await llm.generate_function_call(
                    prompt=message,
                    functions=[WEB_SEARCH_DECISION_FUNCTION],
                    system_prompt=WEB_SEARCH_DECISION_SYSTEM_PROMPT,
                    function_call={"name": "web_search_decision"},
                )

                if func_args is None or not func_args.get("needs_search", False):
                    logger.debug(
                        "Web search skipped (not needed)",
                        extra={"job_id": job_id, "intent": intent},
                    )
                    return {}

                # 최적화된 쿼리 사용
                optimized_query = func_args.get("search_query")
                if optimized_query:
                    search_query = optimized_query

                logger.info(
                    "Web search enrichment triggered",
                    extra={
                        "job_id": job_id,
                        "intent": intent,
                        "query": search_query[:50],
                    },
                )

            except Exception as e:
                logger.warning(
                    f"Web search decision failed, skipping: {e}",
                    extra={"job_id": job_id},
                )
                return {}

        # 3. 웹 검색 실행
        logger.info(
            "Executing web search",
            extra={
                "job_id": job_id,
                "mode": "standalone" if is_standalone else "enrichment",
                "query": search_query[:50],
            },
        )

        result = await _execute_web_search(
            message=search_query,
            job_id=job_id,
        )

        if result is None:
            logger.warning(
                "Web search returned no results",
                extra={"job_id": job_id},
            )
            if event_publisher is not None:
                await event_publisher.notify_stage(
                    task_id=job_id,
                    stage="web_search",
                    status="failed",
                    result={"error": "검색 결과 없음"},
                )
            return {
                "web_search_results": create_error_context(
                    producer="web_search",
                    job_id=job_id,
                    error="검색 결과를 가져오지 못했습니다.",
                ),
            }

        # 4. 결과를 context 채널에 저장
        if event_publisher is not None:
            await event_publisher.notify_stage(
                task_id=job_id,
                stage="web_search",
                status="completed",
                progress=50,
                result={"result_length": len(result)},
                message="웹 검색 완료",
            )

        logger.info(
            "Web search completed",
            extra={
                "job_id": job_id,
                "result_length": len(result),
                "mode": "standalone" if is_standalone else "enrichment",
            },
        )

        return {
            "web_search_results": create_context(
                data={
                    "context": result,
                    "query": search_query,
                    "mode": "standalone" if is_standalone else "enrichment",
                },
                producer="web_search",
                job_id=job_id,
            ),
        }

    # NodeExecutor로 래핑 (Policy 적용: timeout, retry, circuit breaker)
    executor = NodeExecutor.get_instance()

    async def web_search_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (Policy 적용됨)."""
        return await executor.execute(
            node_name="web_search",
            node_func=_web_search_node_inner,
            state=state,
        )

    return web_search_node
