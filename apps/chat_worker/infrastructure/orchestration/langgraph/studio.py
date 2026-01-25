"""LangGraph Studio Factory.

LangGraph Studio Web UI 연동을 위한 단순화된 그래프 팩토리.
`langgraph dev` 명령어로 실행 시 이 모듈이 사용됨.

Usage:
    langgraph dev --host 0.0.0.0 --port 2024 --no-browser

langgraph.json:
    {
        "dependencies": ["."],
        "graphs": {
            "chat": "./chat_worker/infrastructure/orchestration/langgraph/studio.py:create_studio_graph"
        }
    }

Note:
    - 프로덕션 환경에서는 factory.py:create_chat_graph 사용
    - Studio는 시각화/디버깅 용도로만 사용
    - 외부 API 연동 없이 기본 LLM만 사용
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from chat_worker.infrastructure.orchestration.langgraph.state import ChatState

logger = logging.getLogger(__name__)


def create_studio_graph(config: RunnableConfig) -> StateGraph:
    """LangGraph Studio용 단순화된 그래프 생성.

    Args:
        config: LangGraph RunnableConfig (Studio에서 전달)

    Returns:
        컴파일된 StateGraph
    """
    # LLM 클라이언트 생성 (환경변수 기반)
    llm_provider = os.getenv("LLM_PROVIDER", "openai")

    if llm_provider == "google":
        from google import genai

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        model_name = os.getenv("LLM_MODEL", "gemini-3-flash-preview")

        async def llm_generate(prompt: str) -> str:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text or ""

    else:
        import openai

        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model_name = os.getenv("LLM_MODEL", "gpt-5.2")

        async def llm_generate(prompt: str) -> str:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""

    logger.info(f"Studio graph using {llm_provider} ({model_name})")

    # 단순화된 노드 정의
    async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
        """의도 분류 노드."""
        message = state.get("message", "")
        prompt = f"""다음 메시지의 의도를 분류하세요.
카테고리: waste(분리배출), character(캐릭터), location(장소), bulk_waste(대형폐기물), general(일반)

메시지: {message}

한 단어로만 답변하세요."""

        intent = await llm_generate(prompt)
        intent = intent.strip().lower()

        # 유효한 의도인지 확인
        valid_intents = {"waste", "character", "location", "bulk_waste", "general"}
        if intent not in valid_intents:
            intent = "general"

        return {**state, "intent": intent}

    async def router_node(state: dict[str, Any]) -> dict[str, Any]:
        """라우터 노드 (passthrough)."""
        return state

    async def waste_rag_node(state: dict[str, Any]) -> dict[str, Any]:
        """분리배출 RAG 노드 (Studio용 스텁)."""
        return {
            **state,
            "rag_context": "[Studio Mode] 분리배출 정보를 조회했습니다.",
        }

    async def general_node(state: dict[str, Any]) -> dict[str, Any]:
        """일반 응답 노드."""
        return state

    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        """최종 응답 생성 노드."""
        message = state.get("message", "")
        intent = state.get("intent", "general")
        rag_context = state.get("rag_context", "")

        prompt = f"""사용자 질문에 친절하게 답변하세요.

의도: {intent}
컨텍스트: {rag_context}
질문: {message}

답변:"""

        answer = await llm_generate(prompt)
        return {**state, "answer": answer}

    def route_by_intent(state: dict[str, Any]) -> str:
        """의도 기반 라우팅."""
        intent = state.get("intent", "general")
        if intent == "waste":
            return "waste_rag"
        return "general"

    # 그래프 구성
    graph = StateGraph(ChatState)

    graph.add_node("intent", intent_node)
    graph.add_node("router", router_node)
    graph.add_node("waste_rag", waste_rag_node)
    graph.add_node("general", general_node)
    graph.add_node("answer", answer_node)

    graph.set_entry_point("intent")
    graph.add_edge("intent", "router")
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "waste_rag": "waste_rag",
            "general": "general",
        },
    )
    graph.add_edge("waste_rag", "answer")
    graph.add_edge("general", "answer")
    graph.add_edge("answer", END)

    logger.info("Studio graph compiled")
    return graph.compile()
