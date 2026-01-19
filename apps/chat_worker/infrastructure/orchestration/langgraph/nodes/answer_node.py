"""Answer Generation Node - LangGraph 어댑터.

얇은 어댑터: state 변환 + Command 호출.
정책/흐름은 GenerateAnswerCommand(Application)에서 처리.

Clean Architecture:
- Node(Adapter): 이 파일 - LangGraph glue code
- Command(UseCase): GenerateAnswerCommand - 정책/흐름
- Service: AnswerGeneratorService - 순수 비즈니스 로직

토큰 스트리밍 아키텍처:
- answer_node에서 모든 토큰을 직접 발행 (notify_token_v2)
- ProcessChatCommand는 answer 노드의 토큰을 건너뜀 (중복 방지)
- 웹 검색/LangChain 경로 모두 동일한 발행 메커니즘 사용

GENERAL Intent + Native Web Search:
- GENERAL intent에서는 OpenAI Responses API의 네이티브 web_search tool 사용
- generate_with_tools()로 스트리밍 생성 → notify_token_v2()로 직접 토큰 발행
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage, SystemMessage

from chat_worker.application.commands.generate_answer_command import (
    GenerateAnswerCommand,
    GenerateAnswerInput,
    WEB_SEARCH_KEYWORDS,
)
from chat_worker.infrastructure.assets.prompt_loader import PromptBuilder
from chat_worker.infrastructure.orchestration.langgraph.sequence import cleanup_sequence

if TYPE_CHECKING:
    from chat_worker.application.ports.cache import CachePort
    from chat_worker.application.ports.events import ProgressNotifierPort
    from chat_worker.application.ports.llm import LLMClientPort

logger = logging.getLogger(__name__)


def create_answer_node(
    llm: "LLMClientPort",
    cache: "CachePort | None" = None,
    event_publisher: "ProgressNotifierPort | None" = None,
):
    """답변 생성 노드 팩토리.

    Node는 LangGraph 어댑터:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환

    네이티브 스트리밍 환경에서는 Progress/Token 이벤트를
    ProcessChatCommand가 astream_events로 처리합니다.

    GENERAL intent + 웹 검색 키워드:
    - OpenAI Responses API의 네이티브 web_search tool 사용
    - LangGraph가 캡처하지 못하므로 event_publisher로 직접 토큰 발행

    Args:
        llm: LLM 클라이언트
        cache: 캐시 클라이언트 (선택, Answer 캐싱용)
        event_publisher: 이벤트 발행자 (선택, 웹 검색 시 토큰 직접 발행용)

    Returns:
        answer_node 함수
    """
    # Command(UseCase) 인스턴스 생성 - Port 조립
    prompt_builder = PromptBuilder()
    command = GenerateAnswerCommand(
        llm=llm,
        prompt_builder=prompt_builder,
        cache=cache,
    )

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        """LangGraph 노드 (얇은 어댑터).

        역할:
        1. state에서 값 추출 (LangGraph glue)
        2. LLM 호출 및 토큰 직접 발행 (notify_token_v2)
        3. output → state 변환

        Note:
            토큰 스트리밍 아키텍처:
            - answer_node에서 토큰을 직접 발행 (notify_token_v2)
            - ProcessChatCommand는 answer 노드의 토큰을 건너뜀 (중복 방지)
            - 웹 검색/LangChain 경로 모두 동일한 발행 메커니즘 사용

        Args:
            state: 현재 LangGraph 상태

        Returns:
            업데이트된 상태
        """
        job_id = state.get("job_id", "")

        try:
            # 1. state → input DTO 변환
            # recyclable_price_context에서 context 문자열 추출
            price_ctx = state.get("recyclable_price_context")
            price_context_str = price_ctx.get("context") if isinstance(price_ctx, dict) else None

            # bulk_waste_context에서 context 문자열 추출
            waste_ctx = state.get("bulk_waste_context")
            waste_context_str = waste_ctx.get("context") if isinstance(waste_ctx, dict) else None

            # weather_context에서 context 문자열 추출
            weather_ctx = state.get("weather_context")
            weather_context_str = (
                weather_ctx.get("context") if isinstance(weather_ctx, dict) else None
            )

            # collection_point_context에서 context 문자열 추출
            collection_ctx = state.get("collection_point_context")
            collection_context_str = (
                collection_ctx.get("context") if isinstance(collection_ctx, dict) else None
            )

            # 대화 히스토리 추출 (Multi-turn 지원)
            messages = state.get("messages", [])
            conversation_history = None
            if messages:
                # LangChain 메시지 → 간단한 dict 형식으로 변환
                # 최근 10개 메시지만 사용 (토큰 효율성)
                recent_messages = messages[-10:] if len(messages) > 10 else messages
                conversation_history = [
                    {
                        "role": getattr(msg, "type", "user"),
                        "content": getattr(msg, "content", str(msg)),
                    }
                    for msg in recent_messages
                ]

            # 대화 요약 추출 (컨텍스트 압축 시)
            conversation_summary = state.get("summary")

            input_dto = GenerateAnswerInput(
                job_id=job_id,
                message=state.get("message", ""),
                intent=state.get("intent", "general"),
                additional_intents=state.get("additional_intents", []),
                has_multi_intent=state.get("has_multi_intent", False),
                classification=state.get("classification_result"),
                disposal_rules=state.get("disposal_rules"),
                character_context=state.get("character_context"),
                location_context=state.get("location_context"),
                web_search_results=state.get("web_search_results"),
                recyclable_price_context=price_context_str,
                bulk_waste_context=waste_context_str,
                weather_context=weather_context_str,
                collection_point_context=collection_context_str,
                conversation_history=conversation_history,
                conversation_summary=conversation_summary,
            )

            # 2. 프롬프트 준비 (Command에서 컨텍스트 빌드만 수행)
            prepared = await command.prepare(input_dto)

            # 3. 캐시 히트 시 캐시된 답변 반환
            if prepared.cached_answer:
                logger.info(
                    "Answer from cache",
                    extra={"job_id": job_id, "length": len(prepared.cached_answer)},
                )
                cleanup_sequence(job_id)
                return {"answer": prepared.cached_answer}

            # 4. LLM 호출 - 웹 검색 필요 여부에 따라 분기
            intent = state.get("intent", "general")
            message = state.get("message", "")
            message_lower = message.lower()

            # GENERAL intent에서 웹 검색 키워드가 있으면 네이티브 web_search 사용
            needs_web_search = intent == "general" and any(
                kw in message_lower for kw in WEB_SEARCH_KEYWORDS
            )

            answer_parts = []

            if needs_web_search and event_publisher is not None:
                # 네이티브 web_search tool 사용 (OpenAI Responses API)
                # LangGraph가 캡처하지 못하므로 직접 토큰 발행
                logger.info(
                    "Using native web_search tool",
                    extra={"job_id": job_id, "message_preview": message[:50]},
                )

                async for chunk in llm.generate_with_tools(
                    prompt=prepared.prompt,
                    tools=["web_search"],
                    system_prompt=prepared.system_prompt,
                ):
                    if chunk:
                        answer_parts.append(chunk)
                        # 직접 토큰 이벤트 발행 (Redis Streams → Event Router → SSE)
                        await event_publisher.notify_token_v2(
                            task_id=job_id,
                            content=chunk,
                            node="answer",
                        )

                # 토큰 스트림 완료 처리
                await event_publisher.finalize_token_stream(job_id)
            else:
                # LangChain 방식 (answer_node에서 직접 토큰 발행)
                # LangGraph stream_mode="messages" 캡처 대신 직접 발행하여 중복 방지
                langchain_llm = llm.get_langchain_llm()

                # LangChain 메시지 구성
                langchain_messages = []
                if prepared.system_prompt:
                    langchain_messages.append(SystemMessage(content=prepared.system_prompt))
                langchain_messages.append(HumanMessage(content=prepared.prompt))

                # 직접 astream() 호출 및 토큰 발행
                async for chunk in langchain_llm.astream(langchain_messages):
                    content = chunk.content
                    if content:
                        answer_parts.append(content)
                        # 직접 토큰 발행 (ProcessChatCommand와 중복 방지)
                        if event_publisher is not None:
                            await event_publisher.notify_token_v2(
                                task_id=job_id,
                                content=content,
                                node="answer",
                            )

                # 토큰 스트림 완료 처리
                if event_publisher is not None:
                    await event_publisher.finalize_token_stream(job_id)

            answer = "".join(answer_parts)

            # 5. 캐시 저장 (필요한 경우)
            if prepared.is_cacheable and answer:
                await command.save_to_cache(prepared.cache_key, answer)

            logger.info(
                "Answer generated",
                extra={"job_id": job_id, "length": len(answer)},
            )

            # 6. Lamport Clock 정리 (메모리 관리)
            # answer_node는 파이프라인의 마지막 노드이므로 여기서 정리
            cleanup_sequence(job_id)

            # 7. output → state 변환
            return {"answer": answer}

        except Exception as e:
            logger.error(
                "Answer generation failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            # 에러 발생 시에도 Lamport Clock 정리
            cleanup_sequence(job_id)
            return {
                "answer": "답변 생성 중 오류가 발생했습니다. 다시 시도해주세요.",
            }

    return answer_node
