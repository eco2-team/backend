from prometheus_client import Counter, Histogram

REWARD_EVALUATION_TOTAL = Counter(
    "character_reward_evaluation_total",
    "Total number of character reward evaluations",
    ["status", "source"],
)

REWARD_GRANTED_TOTAL = Counter(
    "character_reward_granted_total",
    "Total number of characters granted as rewards",
    ["character_name", "type"],
)

REWARD_PROCESSING_SECONDS = Histogram(
    "character_reward_processing_seconds",
    "Time spent processing reward evaluation",
    ["source"],
)
