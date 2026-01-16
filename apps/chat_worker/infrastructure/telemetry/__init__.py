"""Telemetry - 분산 추적 및 Observability.

OpenTelemetry:
- ADR P2: 노드별 span 속성 추가
- Prometheus/Jaeger 연동

LangSmith:
- LangGraph 네이티브 Observability
- 피처별 (Intent별, Subagent별) 성능 분석
- Token Usage, 비용 추정, Run Comparison

사용 예:
    ```python
    # OpenTelemetry
    from chat_worker.infrastructure.telemetry import get_tracer, with_span

    @with_span("waste_rag_node")
    async def waste_rag_node(state: dict[str, Any]) -> dict[str, Any]:
        ...

    # LangSmith
    from chat_worker.infrastructure.telemetry import (
        configure_langsmith,
        get_run_config,
    )

    configure_langsmith()  # 앱 시작 시
    config = get_run_config(job_id="job-123", intent="waste")
    result = await pipeline.ainvoke(state, config=config)
    ```
"""

from chat_worker.infrastructure.telemetry.tracer import (
    OTEL_ENABLED,
    get_tracer,
    set_span_attributes,
    with_span,
)
from chat_worker.infrastructure.telemetry.langsmith import (
    LANGSMITH_ENABLED,
    LANGSMITH_PROJECT,
    configure_langsmith,
    create_feature_metadata,
    get_feature_info,
    get_run_config,
    get_subagent_tags,
    is_langsmith_enabled,
)
from chat_worker.infrastructure.telemetry.langsmith_adapter import (
    LangSmithTelemetryAdapter,
)

__all__ = [
    # OpenTelemetry
    "OTEL_ENABLED",
    "get_tracer",
    "set_span_attributes",
    "with_span",
    # LangSmith
    "LANGSMITH_ENABLED",
    "LANGSMITH_PROJECT",
    "configure_langsmith",
    "create_feature_metadata",
    "get_feature_info",
    "get_run_config",
    "get_subagent_tags",
    "is_langsmith_enabled",
    # Clean Architecture Adapter
    "LangSmithTelemetryAdapter",
]
