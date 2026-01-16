"""LangSmith Integration - Feature-level Observability.

LangGraph 네이티브 Observability 플랫폼 통합.

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
    )

    # 애플리케이션 시작 시
    configure_langsmith()

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

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# 환경변수 기반 설정
# ─────────────────────────────────────────────────────────────────

LANGSMITH_ENABLED: bool = os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"
LANGSMITH_API_KEY: str | None = os.environ.get("LANGCHAIN_API_KEY")
LANGSMITH_PROJECT: str = os.environ.get("LANGCHAIN_PROJECT", "eco2-chat-worker")
LANGSMITH_ENDPOINT: str = os.environ.get(
    "LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"
)

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
        logger.info(
            "LangSmith tracing disabled (LANGCHAIN_TRACING_V2 not set to 'true')"
        )
        return False

    if not LANGSMITH_API_KEY:
        logger.warning(
            "LangSmith tracing enabled but LANGCHAIN_API_KEY not set - traces will fail"
        )
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
    "LANGSMITH_ENABLED",
    "LANGSMITH_OTEL_ENABLED",
    "LANGSMITH_PROJECT",
    "configure_langsmith",
    "create_feature_metadata",
    "get_feature_info",
    "get_run_config",
    "get_subagent_tags",
    "is_langsmith_enabled",
]
