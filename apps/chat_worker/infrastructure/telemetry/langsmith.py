"""LangSmith Integration - Feature-level Observability.

LangGraph 네이티브 Observability 플랫폼 통합.

추적 메트릭 (LangSmith Dashboard):
- LLM Latency: LLM 호출당 지연 시간
- Cost per Trace: 트레이스당 예상 비용 ($)
- Output Tokens per Trace: 출력 토큰 수
- Input Tokens per Trace: 입력 토큰 수
- Run Count by Tool: 도구/노드별 실행 횟수
- Median Latency by Tool: 도구/노드별 중앙값 지연 시간
- Error Rate by Tool: 도구/노드별 에러율

제공되는 메트릭:
- Per-Node Latency: intent, vision, waste_rag, character, answer 등 노드별 소요시간
- Token Usage: 노드별 input/output 토큰 수, 비용 추정
- Run Timeline: 병렬 실행 (Send API) 시각화
- Error Tracking: 노드별 에러율, 스택 트레이스
- Feedback Loop: RAG 품질 평가, Fallback 체인 추적

설정 방법:
1. 환경변수 설정:
   - LANGCHAIN_TRACING_V2=true
   - LANGCHAIN_API_KEY=<your-api-key>
   - LANGCHAIN_PROJECT=eco2-chat-worker (선택)

2. OpenTelemetry 통합 (Jaeger로 내보내기):
   - LANGSMITH_OTEL_ENABLED=true
   - pip install "langsmith[otel]"
   - LangGraph 트레이스가 OTEL 포맷으로 Jaeger에 전송됨
   - End-to-End: FastAPI → RabbitMQ → LangGraph → LLM 전체 추적 가능

3. LangSmith 대시보드:
   https://smith.langchain.com

4. 피처별 필터링 (LangSmith UI):
   - Metadata: intent=waste, intent=character, ...
   - Tags: subagent:rag, subagent:character, ...

Usage:
    from chat_worker.infrastructure.telemetry.langsmith import (
        configure_langsmith,
        get_run_config,
        is_langsmith_enabled,
        traceable_llm,
        traceable_tool,
    )

    # 애플리케이션 시작 시
    configure_langsmith()

    # LLM 호출 추적
    @traceable_llm(model="gpt-4o-mini")
    async def generate_answer(prompt: str) -> str:
        ...

    # 도구/노드 추적
    @traceable_tool(name="weather_api")
    async def get_weather(location: str) -> dict:
        ...

    # 파이프라인 실행 시
    config = get_run_config(
        job_id="job-123",
        session_id="sess-456",
        user_id="user-789",
        tags=["intent:waste", "subagent:rag"],
    )
    result = await pipeline.ainvoke(state, config=config)
"""

from __future__ import annotations

import functools
import logging
import os
import time
from typing import Any, Callable, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# ─────────────────────────────────────────────────────────────────
# 환경변수 기반 설정
# ─────────────────────────────────────────────────────────────────

LANGSMITH_ENABLED: bool = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
LANGSMITH_API_KEY: str | None = os.environ.get("LANGCHAIN_API_KEY")
LANGSMITH_PROJECT: str = os.environ.get("LANGCHAIN_PROJECT", "eco2-chat-worker")
LANGSMITH_ENDPOINT: str = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

# OpenTelemetry 통합 설정
# LANGSMITH_OTEL_ENABLED=true 시 LangGraph 트레이스가 OTEL로 전송됨
# Jaeger에서 전체 End-to-End 추적 가능 (FastAPI → MQ → LangGraph → LLM)
LANGSMITH_OTEL_ENABLED: bool = os.environ.get("LANGSMITH_OTEL_ENABLED", "").lower() == "true"


def is_langsmith_enabled() -> bool:
    """LangSmith 활성화 여부 확인.

    Returns:
        True if LANGCHAIN_TRACING_V2=true and API key is set
    """
    return LANGSMITH_ENABLED and LANGSMITH_API_KEY is not None


def configure_langsmith() -> bool:
    """LangSmith 설정 적용.

    환경변수 확인 후 설정 상태를 로깅합니다.
    LangSmith는 환경변수 기반으로 자동 활성화되므로
    별도의 초기화 코드는 필요 없습니다.

    OTEL 통합 (LANGSMITH_OTEL_ENABLED=true):
    - LangGraph 트레이스가 OpenTelemetry 포맷으로 전송됨
    - Jaeger에서 전체 흐름 추적 가능
    - 약간의 오버헤드 발생 (성능 중요 시 네이티브 모드 권장)

    Returns:
        True if LangSmith is enabled and configured

    Example:
        ```python
        # main.py 또는 worker 시작점
        from chat_worker.infrastructure.telemetry.langsmith import configure_langsmith

        if configure_langsmith():
            logger.info("LangSmith tracing enabled")
        ```
    """
    if not LANGSMITH_ENABLED:
        logger.info("LangSmith tracing disabled (LANGCHAIN_TRACING_V2 not set to 'true')")
        return False

    if not LANGSMITH_API_KEY:
        logger.warning("LangSmith tracing enabled but LANGCHAIN_API_KEY not set - traces will fail")
        return False

    # OTEL 통합 설정 로깅
    tracing_mode = "otel" if LANGSMITH_OTEL_ENABLED else "native"

    logger.info(
        "LangSmith tracing enabled",
        extra={
            "project": LANGSMITH_PROJECT,
            "endpoint": LANGSMITH_ENDPOINT,
            "otel_enabled": LANGSMITH_OTEL_ENABLED,
            "tracing_mode": tracing_mode,
        },
    )

    if LANGSMITH_OTEL_ENABLED:
        logger.info(
            "LangSmith OTEL mode: LangGraph traces will be sent to Jaeger via OpenTelemetry"
        )

    return True


# ─────────────────────────────────────────────────────────────────
# 모델별 가격 (USD per 1M tokens) - 2025년 1월 기준
# ─────────────────────────────────────────────────────────────────

MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI (USD per 1M tokens)
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Google Gemini 3 (USD per 1M tokens)
    "gemini-3-pro-image-preview": {"input": 2.00, "output": 12.00},
    "gemini-3-flash-preview": {"input": 0.50, "output": 3.00},
    # Google Gemini 2
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    # Google Gemini 1.5
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """토큰 사용량 기반 비용 계산.

    Args:
        model: 모델 이름
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수

    Returns:
        예상 비용 (USD)
    """
    pricing = MODEL_PRICING.get(model, {"input": 1.0, "output": 3.0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


# ─────────────────────────────────────────────────────────────────
# Traceable Decorators - LangSmith 메트릭 자동 추적
# ─────────────────────────────────────────────────────────────────


def traceable_llm(
    model: str = "unknown",
    name: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """LLM 호출 추적 데코레이터.

    LangSmith에서 다음 메트릭을 자동 추적:
    - LLM Latency
    - Input/Output Tokens (response에서 추출)
    - Cost per call
    - Error rate

    Args:
        model: 모델 이름 (비용 계산용)
        name: 트레이스 이름 (기본: 함수명)

    Example:
        ```python
        @traceable_llm(model="gpt-4o-mini")
        async def generate_intent(prompt: str) -> str:
            response = await client.chat.completions.create(...)
            return response
        ```
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        run_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not is_langsmith_enabled():
                return await func(*args, **kwargs)  # type: ignore

            try:
                from langsmith import traceable
                from langsmith.run_helpers import get_current_run_tree
            except ImportError:
                return await func(*args, **kwargs)  # type: ignore

            @traceable(
                run_type="llm",
                name=run_name,
                metadata={"model": model},
                tags=[f"model:{model}", "type:llm"],
            )
            async def traced_func(*a: Any, **kw: Any) -> R:
                start_time = time.perf_counter()
                result = await func(*a, **kw)  # type: ignore
                latency_ms = (time.perf_counter() - start_time) * 1000

                # 토큰 사용량 추출 (OpenAI 응답 형식)
                input_tokens = 0
                output_tokens = 0
                if hasattr(result, "usage") and result.usage:
                    input_tokens = getattr(result.usage, "prompt_tokens", 0)
                    output_tokens = getattr(result.usage, "completion_tokens", 0)

                # 비용 계산
                cost = calculate_cost(model, input_tokens, output_tokens)

                # LangSmith run_tree에 메트릭 추가
                run_tree = get_current_run_tree()
                if run_tree:
                    run_tree.extra = run_tree.extra or {}
                    run_tree.extra["metrics"] = {
                        "latency_ms": latency_ms,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                        "cost_usd": cost,
                    }

                return result

            return await traced_func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # 동기 함수는 추적 없이 실행
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def traceable_tool(
    name: str | None = None,
    tool_type: str = "tool",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """도구/노드 호출 추적 데코레이터.

    LangSmith에서 다음 메트릭을 자동 추적:
    - Run Count by Tool
    - Median Latency by Tool
    - Error Rate by Tool

    Args:
        name: 도구 이름 (기본: 함수명)
        tool_type: 도구 유형 (tool, retriever, chain 등)

    Example:
        ```python
        @traceable_tool(name="weather_api")
        async def get_weather(location: str) -> dict:
            ...

        @traceable_tool(name="waste_rag", tool_type="retriever")
        async def retrieve_waste_info(query: str) -> list:
            ...
        ```
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        run_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not is_langsmith_enabled():
                return await func(*args, **kwargs)  # type: ignore

            try:
                from langsmith import traceable
                from langsmith.run_helpers import get_current_run_tree
            except ImportError:
                return await func(*args, **kwargs)  # type: ignore

            @traceable(
                run_type=tool_type,
                name=run_name,
                tags=[f"tool:{run_name}", f"type:{tool_type}"],
            )
            async def traced_func(*a: Any, **kw: Any) -> R:
                start_time = time.perf_counter()
                error_occurred = False
                try:
                    result = await func(*a, **kw)  # type: ignore
                    return result
                except Exception as e:
                    error_occurred = True
                    raise e
                finally:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    run_tree = get_current_run_tree()
                    if run_tree:
                        run_tree.extra = run_tree.extra or {}
                        run_tree.extra["metrics"] = {
                            "latency_ms": latency_ms,
                            "error": error_occurred,
                        }

            return await traced_func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not is_langsmith_enabled():
                return func(*args, **kwargs)

            try:
                from langsmith import traceable
                from langsmith.run_helpers import get_current_run_tree
            except ImportError:
                return func(*args, **kwargs)

            @traceable(
                run_type=tool_type,
                name=run_name,
                tags=[f"tool:{run_name}", f"type:{tool_type}"],
            )
            def traced_func(*a: Any, **kw: Any) -> R:
                start_time = time.perf_counter()
                error_occurred = False
                try:
                    result = func(*a, **kw)
                    return result
                except Exception as e:
                    error_occurred = True
                    raise e
                finally:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    run_tree = get_current_run_tree()
                    if run_tree:
                        run_tree.extra = run_tree.extra or {}
                        run_tree.extra["metrics"] = {
                            "latency_ms": latency_ms,
                            "error": error_occurred,
                        }

            return traced_func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def track_token_usage(
    run_tree: Any,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float | None = None,
) -> None:
    """수동으로 토큰 사용량 추적.

    @traceable 없이 직접 호출할 때 사용.

    Args:
        run_tree: LangSmith RunTree 객체
        model: 모델 이름
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
        latency_ms: 지연 시간 (ms)

    Example:
        ```python
        from langsmith.run_helpers import get_current_run_tree
        run_tree = get_current_run_tree()
        track_token_usage(run_tree, "gpt-4o-mini", 100, 50, latency_ms=234.5)
        ```
    """
    if not run_tree:
        return

    cost = calculate_cost(model, input_tokens, output_tokens)

    run_tree.extra = run_tree.extra or {}
    run_tree.extra["metrics"] = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cost_usd": cost,
    }
    if latency_ms is not None:
        run_tree.extra["metrics"]["latency_ms"] = latency_ms


def get_run_config(
    job_id: str,
    session_id: str | None = None,
    user_id: str | None = None,
    intent: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LangGraph 실행을 위한 config 생성.

    LangSmith에서 필터링/분석에 사용할 메타데이터를 포함합니다.

    Args:
        job_id: 작업 ID (run_name으로 사용)
        session_id: 세션 ID (thread_id로 사용, 멀티턴 대화 연결)
        user_id: 사용자 ID (메타데이터)
        intent: 분류된 Intent (태그 및 메타데이터)
        tags: 추가 태그 (예: ["subagent:rag", "feature:feedback"])
        metadata: 추가 메타데이터

    Returns:
        LangGraph/LangSmith compatible config dict

    Example:
        ```python
        config = get_run_config(
            job_id="job-123",
            session_id="sess-456",
            user_id="user-789",
            intent="waste",
            tags=["env:production", "version:1.0"],
        )
        result = await pipeline.ainvoke(state, config=config)
        ```
    """
    # 방어적 복사: 원본 리스트 mutation 방지
    run_tags = list(tags) if tags else []

    # Intent를 태그로 추가 (필터링 용이)
    if intent:
        run_tags.append(f"intent:{intent}")

    # 기본 메타데이터
    run_metadata = {
        "job_id": job_id,
        "user_id": user_id,
        "intent": intent,
    }

    # 추가 메타데이터 병합
    if metadata:
        run_metadata.update(metadata)

    config: dict[str, Any] = {
        # LangSmith run identification
        "run_name": f"chat:{job_id}",
        "tags": run_tags,
        "metadata": run_metadata,
        # LangGraph configurable (체크포인터용)
        "configurable": {},
    }

    # 멀티턴 대화를 위한 thread_id
    if session_id:
        config["configurable"]["thread_id"] = session_id

    return config


def get_subagent_tags(
    node_name: str,
    intent: str | None = None,
    is_parallel: bool = False,
) -> list[str]:
    """Subagent 노드용 태그 생성.

    LangSmith에서 Subagent 성능을 필터링할 때 사용합니다.

    Args:
        node_name: 노드 이름 (waste_rag, character, location 등)
        intent: 현재 처리 중인 Intent
        is_parallel: 병렬 실행 여부 (Send API)

    Returns:
        LangSmith 태그 목록

    Example:
        ```python
        tags = get_subagent_tags("waste_rag", intent="waste", is_parallel=True)
        # ['subagent:waste_rag', 'intent:waste', 'execution:parallel']
        ```
    """
    tags = [f"subagent:{node_name}"]

    if intent:
        tags.append(f"intent:{intent}")

    if is_parallel:
        tags.append("execution:parallel")
    else:
        tags.append("execution:sequential")

    return tags


# ─────────────────────────────────────────────────────────────────
# Feature-level Metadata Helpers
# ─────────────────────────────────────────────────────────────────


def create_feature_metadata(
    feature: str,
    sub_feature: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """피처별 메타데이터 생성.

    LangSmith에서 피처별 성능 분석에 사용합니다.

    Args:
        feature: 주요 피처명 (intent, rag, subagent, answer)
        sub_feature: 세부 피처명 (waste, character, location 등)
        **kwargs: 추가 메타데이터

    Returns:
        피처 메타데이터 dict

    Example:
        LangSmith UI에서 필터링:
        - metadata.feature = "rag"
        - metadata.sub_feature = "waste"
    """
    metadata = {
        "feature": feature,
    }

    if sub_feature:
        metadata["sub_feature"] = sub_feature

    metadata.update(kwargs)
    return metadata


# ─────────────────────────────────────────────────────────────────
# Intent-to-Feature Mapping (Load Test 분석용)
# ─────────────────────────────────────────────────────────────────

INTENT_FEATURE_MAP: dict[str, dict[str, Any]] = {
    "waste": {
        "feature": "rag",
        "subagents": ["waste_rag", "weather"],
        "has_feedback": True,
        "description": "분리배출 RAG 검색",
    },
    "bulk_waste": {
        "feature": "external_api",
        "subagents": ["bulk_waste", "weather"],
        "has_feedback": False,
        "description": "대형폐기물 (행정안전부 API)",
    },
    "character": {
        "feature": "grpc",
        "subagents": ["character"],
        "has_feedback": False,
        "description": "캐릭터 정보 (gRPC)",
    },
    "location": {
        "feature": "external_api",
        "subagents": ["location"],
        "has_feedback": False,
        "description": "장소 검색 (카카오맵)",
    },
    "collection_point": {
        "feature": "external_api",
        "subagents": ["collection_point"],
        "has_feedback": False,
        "description": "수거함 위치 (KECO)",
    },
    "recyclable_price": {
        "feature": "external_api",
        "subagents": ["recyclable_price"],
        "has_feedback": False,
        "description": "재활용자원 시세 (KECO)",
    },
    "web_search": {
        "feature": "external_api",
        "subagents": ["web_search"],
        "has_feedback": False,
        "description": "웹 검색 (DuckDuckGo/Tavily)",
    },
    "image_generation": {
        "feature": "llm_generation",
        "subagents": ["image_generation"],
        "has_feedback": False,
        "description": "이미지 생성 (Responses API)",
    },
    "general": {
        "feature": "llm_generation",
        "subagents": ["general"],
        "has_feedback": False,
        "description": "일반 대화",
    },
    "greeting": {
        "feature": "llm_generation",
        "subagents": ["character"],
        "has_feedback": False,
        "description": "인사/캐릭터 소개",
    },
}


def get_feature_info(intent: str) -> dict[str, Any]:
    """Intent에 대한 피처 정보 조회.

    부하테스트 분석 시 Intent별 특성을 파악하는 데 사용합니다.

    Args:
        intent: Intent 이름

    Returns:
        피처 정보 dict (feature, subagents, has_feedback, description)

    Example:
        ```python
        info = get_feature_info("waste")
        # {
        #     "feature": "rag",
        #     "subagents": ["waste_rag", "weather"],
        #     "has_feedback": True,
        #     "description": "분리배출 RAG 검색"
        # }
        ```
    """
    return INTENT_FEATURE_MAP.get(
        intent,
        {
            "feature": "unknown",
            "subagents": ["general"],
            "has_feedback": False,
            "description": f"Unknown intent: {intent}",
        },
    )


__all__ = [
    # 설정
    "LANGSMITH_ENABLED",
    "LANGSMITH_OTEL_ENABLED",
    "LANGSMITH_PROJECT",
    "configure_langsmith",
    "is_langsmith_enabled",
    # 메트릭 추적 데코레이터
    "traceable_llm",
    "traceable_tool",
    "track_token_usage",
    "calculate_cost",
    "MODEL_PRICING",
    # Config 생성
    "get_run_config",
    "get_subagent_tags",
    # 메타데이터
    "create_feature_metadata",
    "get_feature_info",
    "INTENT_FEATURE_MAP",
]
