from __future__ import annotations


from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
)

# Istio가 수집하므로 애플리케이션 레벨 HTTP 메트릭은 제거함.
# 하지만 비즈니스 로직(Custom Metrics) 수집을 위해 Registry와 Endpoint는 유지함.

PROMETHEUS_METRICS_PATH = "/metrics/status"
_FLAG_ATTR = "_observability_metrics_registered"

# 전역 레지스트리 (다른 모듈에서 import하여 커스텀 메트릭 등록 가능)
REGISTRY = CollectorRegistry(auto_describe=True)


def register_http_metrics(
    app: FastAPI,
    *,
    domain: str,
    service: str,
    metrics_path: str = PROMETHEUS_METRICS_PATH,
) -> None:
    """Attach /metrics route to expose Prometheus counters (Custom Metrics only)."""
    if getattr(app.state, _FLAG_ATTR, False):
        return

    # HTTP Request Middleware 제거됨 (Istio Offloading)

    @app.get(metrics_path, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        payload = generate_latest(REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    setattr(app.state, _FLAG_ATTR, True)
