"""Character 도메인 Prometheus 메트릭"""

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)
METRICS_PATH = "/metrics/status"


def register_metrics(app: FastAPI) -> None:
    """Prometheus /metrics 엔드포인트 등록"""

    @app.get(METRICS_PATH, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# ─────────────────────────────────────────────────────────────────────────────
# Character 도메인 커스텀 비즈니스 메트릭
# ─────────────────────────────────────────────────────────────────────────────

REWARD_EVALUATION_TOTAL = Counter(
    "character_reward_evaluation_total",
    "Total number of character reward evaluations",
    ["status", "source"],
    registry=REGISTRY,
)

REWARD_GRANTED_TOTAL = Counter(
    "character_reward_granted_total",
    "Total number of characters granted as rewards",
    ["character_name", "type"],
    registry=REGISTRY,
)

REWARD_PROCESSING_SECONDS = Histogram(
    "character_reward_processing_seconds",
    "Time spent processing reward evaluation",
    ["source"],
    registry=REGISTRY,
)
