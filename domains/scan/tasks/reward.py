"""
DEPRECATED: Reward Task moved to character domain

이 모듈은 더 이상 사용되지 않습니다.
character/consumers/reward.py의 scan_reward_task를 사용하세요.

이유:
- reward 처리는 character 도메인의 책임
- character-worker에서 실행하여 worker-storage 노드에 배치
- CharacterService를 직접 호출하여 gRPC 오버헤드 제거
"""

from __future__ import annotations

import warnings

warnings.warn(
    "domains.scan.tasks.reward is deprecated. "
    "Use domains.character.consumers.reward.scan_reward_task instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backwards compatibility
from domains.character.consumers.reward import (  # noqa: E402
    scan_reward_task as reward_task,
)

__all__ = ["reward_task"]
