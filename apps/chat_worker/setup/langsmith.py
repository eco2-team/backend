"""LangSmith OpenTelemetry Integration.

LangSmith의 LangGraph 추적 데이터를 OpenTelemetry로 내보내
Jaeger에서 LLM 파이프라인 전체 흐름을 추적할 수 있게 합니다.

환경변수 (필수):
- LANGSMITH_TRACING=true: LangSmith 추적 활성화
- LANGSMITH_API_KEY: LangSmith API 키

환경변수 (OTEL 내보내기):
- OTEL_EXPORTER_OTLP_ENDPOINT: Jaeger collector 주소
- LANGSMITH_OTEL_ENABLED=true: OTEL 내보내기 활성화 (자체 플래그)

통합 흐름:
  API Request → MQ Publish → Worker Consume → LangGraph Pipeline → LLM Calls
                    │                               │                  │
                    └── Jaeger ◄────────────────────┴──────────────────┘

LangSmith OTEL 통합 방식:
1. LangSmith → Jaeger: langsmith.run_trees 모듈의 TracerProvider 연동
2. 환경변수 OTEL_EXPORTER_OTLP_ENDPOINT 설정 시 자동 내보내기

참조:
- https://docs.smith.langchain.com/observability/how_to_guides/tracing/trace_with_opentelemetry
- langsmith[otel]>=0.4.25 필요
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Environment variables
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "eco2-chat-worker")
OTEL_EXPORTER_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

# 자체 플래그: LangSmith OTEL 내보내기 활성화 여부
# OTEL_EXPORTER_OTLP_ENDPOINT가 설정되어 있어야 의미 있음
LANGSMITH_OTEL_ENABLED = os.getenv("LANGSMITH_OTEL_ENABLED", "true").lower() == "true"

# Global state
_is_configured = False


def configure_langsmith_otel() -> bool:
    """LangSmith OpenTelemetry 통합 설정.

    LangSmith 추적 데이터를 OpenTelemetry로 내보내도록 설정합니다.
    broker.py의 _setup_aio_pika_tracing()에서 TracerProvider가
    먼저 설정되어 있어야 합니다.

    LangSmith SDK >= 0.4.25에서 OTEL 내보내기 지원:
    - TracerProvider가 설정되어 있으면 자동으로 span 생성
    - LangGraph 노드별 실행이 Jaeger에 표시됨

    Returns:
        bool: 설정 성공 여부
    """
    global _is_configured

    if _is_configured:
        return True

    if not LANGSMITH_TRACING:
        logger.info("LangSmith tracing disabled (LANGSMITH_TRACING=false)")
        return False

    if not LANGSMITH_API_KEY:
        logger.warning("LangSmith API key not set (LANGSMITH_API_KEY)")
        return False

    if not LANGSMITH_OTEL_ENABLED:
        logger.info("LangSmith OTEL export disabled (LANGSMITH_OTEL_ENABLED=false)")
        return False

    if not OTEL_EXPORTER_ENDPOINT:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT not set. "
            "LangSmith traces will not be exported to Jaeger."
        )
        # LangSmith 자체는 활성화, OTEL 내보내기만 비활성화
        _is_configured = True
        return True

    try:
        # LangSmith SDK가 TracerProvider를 감지하여 자동으로 OTEL span 생성
        # 별도 설정 없이 환경변수만으로 동작
        # - LANGCHAIN_TRACING_V2=true (또는 LANGSMITH_TRACING=true)
        # - LANGSMITH_API_KEY 설정
        # - TracerProvider 설정됨 (broker.py에서 설정)

        # LangSmith Client 초기화 확인
        from langsmith import Client

        client = Client(api_key=LANGSMITH_API_KEY)

        # 프로젝트 존재 확인 (선택적)
        try:
            # API 연결 테스트
            client.list_projects(limit=1)
        except Exception:
            # 프로젝트 목록 조회 실패해도 추적은 동작
            pass

        _is_configured = True
        logger.info(
            "LangSmith OTEL integration enabled",
            extra={
                "project": LANGSMITH_PROJECT,
                "otel_endpoint": OTEL_EXPORTER_ENDPOINT,
            },
        )
        return True

    except ImportError as e:
        logger.warning(
            f"LangSmith not available: {e}. "
            "Install: pip install 'langsmith[otel]>=0.4.25'"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to configure LangSmith OTEL: {e}")
        return False


def get_langsmith_run_config(
    job_id: str,
    session_id: str,
    user_id: str,
) -> dict[str, Any]:
    """LangSmith + LangGraph run config 생성.

    LangGraph 실행 시 사용할 config를 생성합니다.
    - run_name: Jaeger/LangSmith에서 표시될 이름
    - tags: 필터링용 태그
    - metadata: 추가 컨텍스트

    Args:
        job_id: 작업 ID
        session_id: 세션 ID
        user_id: 사용자 ID

    Returns:
        LangGraph config dict
    """
    config: dict[str, Any] = {
        "run_name": f"chat-{job_id[:8]}",
        "tags": ["chat-worker", "langgraph"],
        "metadata": {
            "job_id": job_id,
            "session_id": session_id,
            "user_id": user_id,
        },
        "configurable": {},
    }

    # Multi-turn 대화용 thread_id 설정
    if session_id:
        config["configurable"]["thread_id"] = session_id

    return config


class TelemetryConfig:
    """Telemetry 설정 포트 구현.

    ProcessChatCommand에서 사용하는 TelemetryConfigPort 구현체.
    """

    def get_run_config(
        self,
        job_id: str,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """LangGraph run config 반환."""
        return get_langsmith_run_config(job_id, session_id, user_id)
