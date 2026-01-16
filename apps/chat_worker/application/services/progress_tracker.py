"""Dynamic Progress Tracker - Phase 기반 Progress 계산.

동적 라우팅(Send API) 환경에서 서브에이전트 병렬 실행 시
Progress를 정확하게 계산합니다.

아키텍처:
```
Phase 1: Understanding (0-20%)
  └─ queued, intent, vision

Phase 2: Information Gathering (20-55%)
  └─ subagents 병렬 실행
  └─ progress = 20 + (completed/total) * 35

Phase 3: Synthesis (55-100%)
  └─ aggregator, summarize, answer, done
```

사용 예시:
```python
tracker = DynamicProgressTracker()

# 서브에이전트 시작 추적
tracker.on_subagent_start("waste_rag")
tracker.on_subagent_start("weather")

# Progress 계산
progress = tracker.calculate_progress("subagents", "started")  # 20

# 서브에이전트 완료
tracker.on_subagent_end("weather")
progress = tracker.calculate_progress("subagents", "completed")  # 37 (1/2)

tracker.on_subagent_end("waste_rag")
progress = tracker.calculate_progress("subagents", "completed")  # 55 (2/2)
```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseProgress:
    """Phase별 Progress 범위."""

    start: int
    end: int


# Phase 기반 Progress 정의
PHASE_PROGRESS: dict[str, PhaseProgress] = {
    # Phase 1: Understanding (0-20%)
    "queued": PhaseProgress(0, 0),
    "intent": PhaseProgress(5, 15),
    "vision": PhaseProgress(15, 20),
    # Phase 2: Information Gathering (20-55%)
    # 동적 라우팅으로 1~10개 노드 병렬 실행
    # 완료된 노드 수 기반으로 진행률 보간
    "subagents": PhaseProgress(20, 55),
    # Phase 3: Synthesis (55-100%)
    "aggregator": PhaseProgress(55, 65),
    "summarize": PhaseProgress(65, 75),
    "answer": PhaseProgress(75, 95),
    "done": PhaseProgress(100, 100),
}

# 서브에이전트 노드 목록 (Send API 대상)
SUBAGENT_NODES: frozenset[str] = frozenset(
    {
        "waste_rag",
        "character",
        "location",
        "bulk_waste",
        "weather",
        "web_search",
        "collection_point",
        "recyclable_price",
        "image_generation",
        "general",
        "feedback",
    }
)

# 노드명 → Phase 매핑 (서브에이전트 외)
NODE_TO_PHASE: dict[str, str] = {
    "intent": "intent",
    "vision": "vision",
    "router": "subagents",  # router 완료 = subagents 시작
    "aggregator": "aggregator",
    "summarize": "summarize",
    "answer": "answer",
}

# 노드별 UI 메시지 (i18n: 추후 YAML 파일로 외부화 가능)
NODE_MESSAGES: dict[str, dict[str, str]] = {
    "intent": {
        "started": "의도를 분석하고 있습니다...",
        "completed": "의도 분석 완료",
    },
    "vision": {
        "started": "이미지를 분석하고 있습니다...",
        "completed": "이미지 분석 완료",
    },
    "waste_rag": {
        "started": "분리배출 정보를 검색하고 있습니다...",
        "completed": "분리배출 정보 검색 완료",
    },
    "character": {
        "started": "캐릭터 정보를 불러오고 있습니다...",
        "completed": "캐릭터 정보 로드 완료",
    },
    "location": {
        "started": "위치 정보를 확인하고 있습니다...",
        "completed": "위치 정보 확인 완료",
    },
    "weather": {
        "started": "날씨 정보를 조회하고 있습니다...",
        "completed": "날씨 정보 조회 완료",
    },
    "web_search": {
        "started": "웹에서 정보를 검색하고 있습니다...",
        "completed": "웹 검색 완료",
    },
    "collection_point": {
        "started": "수거 지점을 검색하고 있습니다...",
        "completed": "수거 지점 검색 완료",
    },
    "bulk_waste": {
        "started": "대형 폐기물 정보를 조회하고 있습니다...",
        "completed": "대형 폐기물 정보 조회 완료",
    },
    "recyclable_price": {
        "started": "재활용품 시세를 조회하고 있습니다...",
        "completed": "재활용품 시세 조회 완료",
    },
    "image_generation": {
        "started": "이미지를 생성하고 있습니다...",
        "completed": "이미지 생성 완료",
    },
    "aggregator": {
        "started": "정보를 종합하고 있습니다...",
        "completed": "정보 종합 완료",
    },
    "summarize": {
        "started": "답변을 요약하고 있습니다...",
        "completed": "요약 완료",
    },
    "answer": {
        "started": "답변을 생성하고 있습니다...",
        "completed": "답변 생성 완료",
    },
}


def get_node_message(node: str, status: str) -> str:
    """노드별 UI 메시지 조회.

    Args:
        node: 노드명
        status: started | completed

    Returns:
        사용자에게 표시할 메시지
    """
    node_messages = NODE_MESSAGES.get(node, {})
    return node_messages.get(status, f"{node} {status}")


@dataclass
class DynamicProgressTracker:
    """동적 라우팅 환경의 Progress 추적기.

    Send API로 병렬 실행되는 서브에이전트들의 진행률을
    동적으로 계산합니다.

    Attributes:
        _activated_subagents: 시작된 서브에이전트 노드 집합
        _completed_subagents: 완료된 서브에이전트 노드 집합
    """

    _activated_subagents: set[str] = field(default_factory=set)
    _completed_subagents: set[str] = field(default_factory=set)

    # 클래스 상수
    PHASE_PROGRESS: ClassVar[dict[str, PhaseProgress]] = PHASE_PROGRESS
    SUBAGENT_NODES: ClassVar[frozenset[str]] = SUBAGENT_NODES

    def on_subagent_start(self, node: str) -> None:
        """서브에이전트 시작 추적.

        Args:
            node: 시작된 노드명
        """
        if node in SUBAGENT_NODES:
            self._activated_subagents.add(node)
            logger.debug(
                "Subagent started",
                extra={
                    "node": node,
                    "activated": len(self._activated_subagents),
                    "completed": len(self._completed_subagents),
                },
            )

    def on_subagent_end(self, node: str) -> None:
        """서브에이전트 완료 추적.

        Args:
            node: 완료된 노드명
        """
        if node in SUBAGENT_NODES:
            self._completed_subagents.add(node)
            logger.debug(
                "Subagent completed",
                extra={
                    "node": node,
                    "activated": len(self._activated_subagents),
                    "completed": len(self._completed_subagents),
                },
            )

    def is_subagent(self, node: str) -> bool:
        """노드가 서브에이전트인지 확인.

        Args:
            node: 노드명

        Returns:
            서브에이전트 여부
        """
        return node in SUBAGENT_NODES

    def get_phase_for_node(self, node: str) -> str:
        """노드에 해당하는 Phase 반환.

        Args:
            node: 노드명

        Returns:
            Phase명 (intent, subagents, answer 등)
        """
        if node in SUBAGENT_NODES:
            return "subagents"
        return NODE_TO_PHASE.get(node, "subagents")

    def calculate_progress(self, phase: str, status: str) -> int:
        """Phase와 상태에 따른 Progress 계산.

        Args:
            phase: 현재 Phase (intent, subagents, answer, ...)
            status: 상태 (started, completed)

        Returns:
            Progress 값 (0-100)
        """
        if phase not in PHASE_PROGRESS:
            logger.warning("Unknown phase: %s", phase)
            return 0

        phase_range = PHASE_PROGRESS[phase]

        # 서브에이전트 Phase: 동적 계산
        if phase == "subagents":
            return self._calculate_subagent_progress()

        # 기타 Phase: 시작/완료에 따른 고정값
        return phase_range.start if status == "started" else phase_range.end

    def _calculate_subagent_progress(self) -> int:
        """서브에이전트 병렬 실행 진행률 계산.

        공식: base + (completed / total) * range

        예시:
          - 3개 활성화, 1개 완료: 20 + (1/3) * 35 ≈ 32%
          - 5개 활성화, 3개 완료: 20 + (3/5) * 35 = 41%
          - 1개 활성화, 1개 완료: 20 + (1/1) * 35 = 55%

        Returns:
            Progress 값 (20-55)
        """
        total = len(self._activated_subagents)
        completed = len(self._completed_subagents)

        if total == 0:
            # 아직 서브에이전트 시작 안됨 → 시작 값
            return PHASE_PROGRESS["subagents"].start

        phase = PHASE_PROGRESS["subagents"]
        range_size = phase.end - phase.start  # 35

        progress = phase.start + int((completed / total) * range_size)

        logger.debug(
            "Subagent progress calculated",
            extra={
                "total": total,
                "completed": completed,
                "progress": progress,
            },
        )

        return progress

    def get_subagent_status(self) -> dict[str, int | list[str]]:
        """서브에이전트 상태 반환 (UI용).

        Returns:
            상태 딕셔너리: {total, completed, active}
        """
        return {
            "total": len(self._activated_subagents),
            "completed": len(self._completed_subagents),
            "active": list(self._activated_subagents - self._completed_subagents),
        }

    def reset(self) -> None:
        """추적 상태 초기화."""
        self._activated_subagents.clear()
        self._completed_subagents.clear()


__all__ = [
    "DynamicProgressTracker",
    "PhaseProgress",
    "PHASE_PROGRESS",
    "SUBAGENT_NODES",
    "NODE_TO_PHASE",
    "NODE_MESSAGES",
    "get_node_message",
]
