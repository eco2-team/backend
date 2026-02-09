"""PostgreSQL Eval Result Adapter - L3 Cold Storage.

asyncpg Pool 기반 평가 결과 영구 저장.
Redis miss 시 PG fallback 역할.

See: docs/plans/chat-eval-pipeline-plan.md §5.1 (Layered Memory)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class PostgresEvalResultAdapter:
    """PostgreSQL L3 Cold Storage for Eval Results.

    asyncpg 커넥션 풀 기반.
    save_result / save_drift_log: INSERT
    get_intent_distribution / get_recent_scores: SELECT (Redis fallback)
    """

    def __init__(self, pool: "asyncpg.Pool") -> None:
        """초기화.

        Args:
            pool: asyncpg 커넥션 풀
        """
        self._pool = pool

    async def save_result(self, eval_result_dict: dict[str, Any]) -> None:
        """평가 결과 INSERT.

        Args:
            eval_result_dict: EvalResult.to_dict() 결과
        """
        query = """
            INSERT INTO chat.eval_results (
                job_id, intent, grade, continuous_score, axis_scores,
                eval_mode, model_version, prompt_version,
                eval_duration_ms, eval_cost_usd, calibration_status,
                code_grader_result, llm_grader_result, metadata
            ) VALUES (
                $1, $2, $3, $4, $5::jsonb,
                $6, $7, $8,
                $9, $10, $11,
                $12::jsonb, $13::jsonb, $14::jsonb
            )
        """
        metadata = eval_result_dict.get("metadata", {})
        await self._pool.execute(
            query,
            metadata.get("job_id", "00000000-0000-0000-0000-000000000000"),
            metadata.get("intent", ""),
            eval_result_dict["grade"],
            eval_result_dict["continuous_score"],
            json.dumps(eval_result_dict.get("axis_scores", {})),
            metadata.get("eval_mode", "async"),
            eval_result_dict.get("model_version", "unknown"),
            eval_result_dict.get("prompt_version", "unknown"),
            eval_result_dict.get("eval_duration_ms", 0),
            eval_result_dict.get("eval_cost_usd"),
            eval_result_dict.get("calibration_status"),
            (
                json.dumps(eval_result_dict.get("code_grader_result"))
                if eval_result_dict.get("code_grader_result")
                else None
            ),
            (
                json.dumps(eval_result_dict.get("llm_grader_result"))
                if eval_result_dict.get("llm_grader_result")
                else None
            ),
            json.dumps(metadata),
        )

    async def save_drift_log(self, drift_entry: dict[str, Any]) -> None:
        """Calibration Drift 로그 INSERT.

        Args:
            drift_entry: drift 탐지 정보
        """
        query = """
            INSERT INTO chat.calibration_drift_log (
                axis, severity, cusum_positive, cusum_negative,
                sample_count, action_taken, calibration_version, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        """
        await self._pool.execute(
            query,
            drift_entry.get("axis", "unknown"),
            drift_entry.get("severity", "OK"),
            drift_entry.get("cusum_positive", 0.0),
            drift_entry.get("cusum_negative", 0.0),
            drift_entry.get("sample_count", 0),
            drift_entry.get("action_taken"),
            drift_entry.get("calibration_version"),
            json.dumps(drift_entry.get("metadata", {})),
        )

    async def get_intent_distribution(self, days: int = 7) -> dict[str, float]:
        """최근 N일간 Intent별 트래픽 비율.

        Args:
            days: 조회 기간 (기본 7일)

        Returns:
            intent -> 비율 매핑
        """
        since = datetime.now(tz=UTC) - timedelta(days=days)
        query = """
            SELECT intent, COUNT(*)::float / SUM(COUNT(*)) OVER () AS ratio
            FROM chat.eval_results
            WHERE created_at >= $1 AND intent != ''
            GROUP BY intent
            ORDER BY ratio DESC
        """
        rows = await self._pool.fetch(query, since)
        return {row["intent"]: float(row["ratio"]) for row in rows}

    async def get_recent_scores(self, axis: str, n: int = 10) -> list[float]:
        """특정 축의 최근 N개 점수 조회 (PG fallback).

        JSONB에서 축별 점수 추출.

        Args:
            axis: 평가 축 이름
            n: 조회할 개수

        Returns:
            최근 N개 점수 리스트 (최신순)
        """
        query = """
            SELECT (axis_scores->$1->>'score')::float AS score
            FROM chat.eval_results
            WHERE axis_scores ? $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        rows = await self._pool.fetch(query, axis, n)
        return [float(row["score"]) for row in rows if row["score"] is not None]


__all__ = ["PostgresEvalResultAdapter"]
