"""Eval Config DTO.

Eval Pipeline Feature Flag 및 실행 설정.
factory.py에서 주입하여 eval_node 동작 제어.

참조: docs/plans/chat-eval-pipeline-plan.md Section 2.1

3가지 실행 모드:
- sync: L1 Code Grader만 동기 실행. C등급 시 재생성 1회. < 50ms.
- async: L1 동기 + L2/L3를 Celery Worker로 비동기. Production 품질 추적.
- shadow: L1+L2+L3 모두 비동기. 응답에 영향 없음. 로그만. A/B 테스트.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class EvalConfig:
    """Eval Pipeline Feature Flag 및 실행 설정.

    Attributes:
        enable_eval_pipeline: Eval Pipeline 활성화 여부
        eval_mode: 실행 모드 (sync/async/shadow)
        eval_sample_rate: 평가 샘플링 비율 (0.0~1.0, 비용 제어)
        eval_llm_grader_enabled: L2 LLM Grader 활성화 여부
        eval_regeneration_enabled: C등급 재생성 활성화 (sync 모드 전용)
        eval_model: 평가용 LLM 모델 ID
        eval_temperature: 평가 LLM temperature (낮을수록 일관)
        eval_max_tokens: 평가 LLM max tokens
        eval_self_consistency_runs: Self-Consistency 채점 횟수 (고위험 구간)
        eval_cusum_check_interval: N번째 요청마다 Calibration 실행
        eval_cost_budget_daily_usd: 일일 평가 비용 상한 (USD)
    """

    enable_eval_pipeline: bool = False
    eval_mode: Literal["sync", "async", "shadow"] = "async"
    eval_sample_rate: float = 1.0
    eval_llm_grader_enabled: bool = True
    eval_regeneration_enabled: bool = False
    eval_model: str = "gpt-5.2"
    eval_temperature: float = 0.1
    eval_max_tokens: int = 1000
    eval_self_consistency_runs: int = 3
    eval_cusum_check_interval: int = 100
    eval_cost_budget_daily_usd: float = 50.0


__all__ = ["EvalConfig"]
