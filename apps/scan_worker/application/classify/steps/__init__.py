"""Classify Steps - 파이프라인 단계 구현.

각 Step은 필요 시 직접 import:
    from scan_worker.application.classify.steps.vision_step import VisionStep
    from scan_worker.application.classify.steps.rule_step import RuleStep
    from scan_worker.application.classify.steps.answer_step import AnswerStep
    from scan_worker.application.classify.steps.reward_step import RewardStep

Note: 외부 의존성(yaml, celery 등) 때문에 lazy import 권장.
"""

__all__ = [
    "VisionStep",
    "RuleStep",
    "AnswerStep",
    "RewardStep",
]


def __getattr__(name: str):
    """Lazy import로 의존성 지연 로딩."""
    if name == "VisionStep":
        from scan_worker.application.classify.steps.vision_step import VisionStep

        return VisionStep
    elif name == "RuleStep":
        from scan_worker.application.classify.steps.rule_step import RuleStep

        return RuleStep
    elif name == "AnswerStep":
        from scan_worker.application.classify.steps.answer_step import AnswerStep

        return AnswerStep
    elif name == "RewardStep":
        from scan_worker.application.classify.steps.reward_step import RewardStep

        return RewardStep
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
