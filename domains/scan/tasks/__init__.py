"""Scan domain Celery tasks.

Phase 2: 4단계 파이프라인 (Celery Chain)
- vision_task: GPT Vision 이미지 분류
- rule_task: RAG 기반 배출 규정 검색
- answer_task: 최종 답변 생성
- scan_reward_task: 캐릭터 보상 평가 (로컬 캐시 사용)
"""

from domains.scan.tasks.answer import answer_task
from domains.scan.tasks.reward import scan_reward_task
from domains.scan.tasks.rule import rule_task
from domains.scan.tasks.vision import vision_task

__all__ = [
    "vision_task",
    "rule_task",
    "answer_task",
    "scan_reward_task",
]
