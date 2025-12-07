from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

PROMETHEUS_METRICS_PATH = "/metrics/status"

_FLAG_ATTR = "_observability_metrics_registered"
_DEFAULT_BUCKETS = tuple(
    [x / 100.0 for x in range(5, 500, 5)]  # 0.05 ~ 4.95 (0.05 step)
    + [x / 10.0 for x in range(50, 301, 1)]  # 5.0 ~ 30.0 (0.1 step)
)

REGISTRY = CollectorRegistry(auto_describe=True)

REQUEST_COUNTER = Counter(
    "http_requests_total",
    "Domain API HTTP request count",
    ("domain", "service", "method", "path", "status_class", "status_code"),
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Domain API HTTP request latency in seconds",
    ("domain", "service", "method", "path"),
    registry=REGISTRY,
    buckets=_DEFAULT_BUCKETS,
)


def register_http_metrics(
    app: FastAPI,
    *,
    domain: str,
    service: str,
    metrics_path: str = PROMETHEUS_METRICS_PATH,
) -> None:
    """Attach middleware + /metrics route to expose Prometheus counters."""
    if getattr(app.state, _FLAG_ATTR, False):
        return

    @app.middleware("http")
    async def _metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ):
        if request.url.path == metrics_path:
            return await call_next(request)
        route_path = _resolve_route_path(request)
        method = request.method.upper()
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except HTTPException as exc:  # FastAPI raises for 4xx scenarios
            duration = time.perf_counter() - start_time
            _observe_request(
                domain=domain,
                service=service,
                method=method,
                path=route_path,
                status_code=exc.status_code,
                duration=duration,
            )
            raise
        except Exception:
            duration = time.perf_counter() - start_time
            _observe_request(
                domain=domain,
                service=service,
                method=method,
                path=route_path,
                status_code=500,
                duration=duration,
            )
            raise
        else:
            duration = time.perf_counter() - start_time
            _observe_request(
                domain=domain,
                service=service,
                method=method,
                path=route_path,
                status_code=response.status_code,
                duration=duration,
            )
            return response

    @app.get(metrics_path, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        payload = generate_latest(REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    setattr(app.state, _FLAG_ATTR, True)


def _observe_request(
    *,
    domain: str,
    service: str,
    method: str,
    path: str,
    status_code: int,
    duration: float,
) -> None:
    status_class = _status_class(status_code)
    REQUEST_COUNTER.labels(
        domain=domain,
        service=service,
        method=method,
        path=path,
        status_class=status_class,
        status_code=str(status_code),
    ).inc()
    REQUEST_LATENCY.labels(
        domain=domain,
        service=service,
        method=method,
        path=path,
    ).observe(duration)


def _status_class(status_code: int) -> str:
    bucket = status_code // 100
    if bucket == 0:
        return "unknown"
    return f"{bucket}xx"


def _resolve_route_path(request: Request) -> str:
    route = request.scope.get("route")
    path_attr = getattr(route, "path", None)
    if path_attr:
        return path_attr
    return request.url.path
