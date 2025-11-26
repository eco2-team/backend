from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class WasteClassificationResult(BaseModel):
    """Result payload produced by the waste-classification pipeline."""

    classification_result: Dict[str, Any] = Field(
        default_factory=dict,
        description="Vision 모델이 반환한 분류 정보",
    )
    disposal_rules: Dict[str, Any] = Field(
        default_factory=dict,
        description="Lite RAG에서 매칭된 배출 규정",
    )
    final_answer: Dict[str, Any] = Field(
        default_factory=dict,
        description="사용자 안내문",
    )
