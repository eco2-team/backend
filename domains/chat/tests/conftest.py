"""Pytest fixtures for Chat domain tests."""

import os
import sys
from pathlib import Path

import pytest

# pytest-asyncio 조건부 로드 (CI에서 미설치 시 graceful skip)
try:
    import pytest_asyncio  # noqa: F401

    pytest_plugins = ("pytest_asyncio",)
except ImportError:
    pytest_asyncio = None

# 프로젝트 루트를 PYTHONPATH에 추가
ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 테스트 환경 설정
os.environ["OTEL_ENABLED"] = "false"
os.environ["AUTH_DISABLED"] = "true"

# Integration 테스트 디렉토리 기본 제외 (OPENAI_API_KEY 필요)
# 실행: pytest domains/chat/tests/integration/ -v -s
collect_ignore = ["integration"]


@pytest.fixture
def mock_classification_result() -> dict:
    """Vision/Text 파이프라인 결과 mock"""
    return {
        "classification_result": {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "무색페트병",
                "minor_category": "음료수병",
            },
            "situation_tags": ["내용물_없음", "라벨_제거됨"],
        },
        "disposal_rules": {
            "배출방법_공통": "내용물을 비우고 라벨을 제거",
            "배출방법_세부": "투명 페트병 전용 수거함에 배출",
        },
        "final_answer": {
            "user_answer": "페트병은 내용물을 비우고 라벨을 제거한 후 투명 페트병 수거함에 버려주세요."
        },
    }
