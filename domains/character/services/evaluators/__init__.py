"""Reward Evaluator Strategy Pattern.

리워드 소스별 평가 로직을 분리하여 확장성을 제공합니다.

Usage:
    from domains.character.services.evaluators import get_evaluator

    evaluator = get_evaluator(CharacterRewardSource.SCAN)
    characters = await character_repo.list_all()
    result = evaluator.evaluate(payload, characters)

Architecture:
    CharacterRewardSource
    ├── SCAN   → ScanRewardEvaluator (source_label: "scan-reward")
    ├── QUEST  → QuestRewardEvaluator (향후)
    └── EVENT  → EventRewardEvaluator (향후)
"""

from domains.character.services.evaluators.base import (
    EvaluationResult,
    RewardEvaluator,
)
from domains.character.services.evaluators.registry import (
    clear_registry,
    get_evaluator,
    register_evaluator,
    reset_registry,
)
from domains.character.services.evaluators.scan import ScanRewardEvaluator

__all__ = [
    "EvaluationResult",
    "RewardEvaluator",
    "ScanRewardEvaluator",
    "clear_registry",
    "get_evaluator",
    "register_evaluator",
    "reset_registry",
]
