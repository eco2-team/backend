from prometheus_client import Histogram, Counter
from domains._shared.observability.metrics import REGISTRY

PIPELINE_STEP_LATENCY = Histogram(
    "scan_pipeline_step_duration_seconds",
    "Duration of each step in the waste classification pipeline",
    labelnames=["step"],
    registry=REGISTRY,
    buckets=(0.1, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.5, 15.0, 20.0),
)

REWARD_MATCH_LATENCY = Histogram(
    "scan_reward_match_duration_seconds",
    "Duration of character reward matching API call",
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

REWARD_MATCH_COUNTER = Counter(
    "scan_reward_match_total",
    "Total count of character reward matching attempts",
    labelnames=["status"],  # success, failed, skipped
    registry=REGISTRY,
)
