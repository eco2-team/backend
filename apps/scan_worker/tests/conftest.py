"""Pytest Configuration for Scan Worker Tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add backend root to path for imports
backend_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_root))


@pytest.fixture
def sample_classification():
    """샘플 분류 결과."""
    return {
        "classification": {
            "major_category": "재활용폐기물",
            "middle_category": "플라스틱류",
            "minor_category": "페트병",
        },
        "situation_tags": ["깨끗한 상태", "라벨 부착"],
        "meta": {"user_input": "이 페트병은 어떻게 버리나요?"},
    }


@pytest.fixture
def sample_disposal_rules():
    """샘플 배출 규정."""
    return {
        "규정명": "플라스틱류 배출 규정",
        "배출방법": "내용물 비우고 물로 헹궈서 배출",
        "주의사항": "라벨 제거 필요",
    }


@pytest.fixture
def sample_answer():
    """샘플 답변."""
    return {
        "disposal_steps": {
            "단계1": "내용물을 비웁니다.",
            "단계2": "물로 깨끗이 헹굽니다.",
            "단계3": "라벨을 제거합니다.",
            "단계4": "분리수거함에 배출합니다.",
        },
        "insufficiencies": [],
        "user_answer": "페트병은 내용물을 비우고 물로 헹군 후 라벨을 제거하여 분리수거함에 배출하세요.",
    }
