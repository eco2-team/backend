"""Pytest fixtures for Scan service tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

# pytest-asyncio 조건부 로드 (CI에서 미설치 시 graceful skip)
try:
    import pytest_asyncio  # noqa: F401

    pytest_plugins = ("pytest_asyncio",)
except ImportError:
    pytest_asyncio = None

# Add project paths for imports
SERVICE_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
for path in (SERVICE_ROOT, DOMAIN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# 테스트 환경 설정
os.environ["OTEL_ENABLED"] = "false"
os.environ["SCAN_AUTH_DISABLED"] = "true"

if TYPE_CHECKING:
    from domains.scan.core.config import Settings


@pytest.fixture(autouse=True)
def reset_global_state():
    """모든 테스트 전후로 글로벌 상태를 리셋 (테스트 격리)."""
    from domains.scan.core.grpc_client import reset_character_client

    reset_character_client()
    yield
    reset_character_client()


@pytest.fixture
def test_user_id() -> UUID:
    """테스트용 사용자 ID."""
    return UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def test_task_id() -> UUID:
    """테스트용 태스크 ID."""
    return uuid4()


@pytest.fixture
def mock_settings() -> "Settings":
    """테스트용 Settings mock."""
    from domains.scan.core.config import Settings

    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        character_grpc_target="localhost:50051",
        reward_feature_enabled=True,
        grpc_timeout_seconds=1.0,
        grpc_max_retries=1,
        grpc_circuit_fail_max=3,
    )


@pytest.fixture
def mock_repository() -> MagicMock:
    """Mock ScanTaskRepository."""
    repo = MagicMock()
    repo.create = AsyncMock(return_value=None)
    repo.update_completed = AsyncMock(return_value=None)
    repo.update_failed = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock(return_value=None)
    repo.count_completed = AsyncMock(return_value=10)
    repo.get_last_completed_at = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_pipeline_result() -> dict:
    """파이프라인 성공 결과 Mock 데이터."""
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
            "user_answer": "페트병은 내용물을 비우고 라벨을 제거한 후 투명 페트병 수거함에 버려주세요.",
            "insufficiencies": [],
        },
        "metadata": {
            "duration_vision": 2.5,
            "duration_rag": 0.3,
            "duration_answer": 3.0,
            "duration_total": 5.8,
        },
    }


@pytest.fixture
def mock_reward_response() -> dict:
    """캐릭터 리워드 응답 Mock 데이터."""
    return {
        "received": True,
        "already_owned": False,
        "name": "페트병이",
        "dialog": "투명 페트병은 라벨을 제거하고 깨끗하게 버려주세요!",
        "match_reason": "무색페트병",
        "character_type": "recyclable",
        "type": "normal",
    }


@pytest.fixture
def valid_image_url() -> str:
    """검증을 통과하는 테스트용 이미지 URL."""
    return "https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg"


@pytest.fixture
def invalid_image_url() -> str:
    """검증 실패하는 이미지 URL."""
    return "http://localhost/malicious.jpg"
