"""Scan domain Celery tasks.

AI 파이프라인을 비동기 태스크로 실행합니다.

Tasks:
    - vision_scan: GPT Vision 분석
    - rule_match: Rule-based RAG 매칭
    - answer_gen: GPT Answer 생성
    - reward_grant: 리워드 지급 (독립 재시도)
"""

from domains.scan.tasks.classification import (
    answer_gen,
    rule_match,
    run_classification_pipeline,
    vision_scan,
)
from domains.scan.tasks.reward import reward_grant

__all__ = [
    "vision_scan",
    "rule_match",
    "answer_gen",
    "run_classification_pipeline",
    "reward_grant",
]
