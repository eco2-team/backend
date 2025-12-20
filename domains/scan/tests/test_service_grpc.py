"""gRPC integration test for ScanService."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from domains.scan.core.config import Settings
from domains.scan.core.validators import ImageUrlValidator
from domains.scan.schemas.scan import ClassificationRequest
from domains.scan.services.scan import ScanService

# Add domain paths for import resolution
sys.path.append(str(Path(__file__).resolve().parents[2]))


@pytest.mark.asyncio
async def test_scan_service_grpc_call():
    """ScanService가 gRPC 클라이언트를 통해 캐릭터 리워드를 요청하는지 테스트."""
    # Arrange
    user_id = uuid4()
    mock_settings = Settings(
        reward_feature_enabled=True,
        character_api_timeout_seconds=5.0,
    )

    # Mock repository
    mock_repository = MagicMock()
    mock_repository.create = AsyncMock(return_value=None)
    mock_repository.update_completed = AsyncMock(return_value=None)

    # Create service with injected dependencies
    service = ScanService.__new__(ScanService)
    service.settings = mock_settings
    service.repository = mock_repository
    service.image_validator = ImageUrlValidator(mock_settings)

    # Mock payload (유효한 이미지 URL 형식)
    payload = ClassificationRequest(
        image_url="https://images.dev.growbin.app/scan/a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.jpg",
        user_input="test",
    )

    # Mock gRPC response
    mock_grpc_response = MagicMock()
    mock_grpc_response.received = True
    mock_grpc_response.already_owned = False
    mock_grpc_response.name = "TestChar"
    mock_grpc_response.HasField.side_effect = lambda field: field in [
        "name",
        "match_reason",
        "character_type",
    ]
    mock_grpc_response.match_reason = "TestReason"
    mock_grpc_response.character_type = "RECYCLING"
    mock_grpc_response.type = "RECYCLING"

    # Mock gRPC client
    mock_client = MagicMock()
    mock_client.get_character_reward = AsyncMock(return_value=mock_grpc_response)

    # Mock waste pipeline result (to trigger reward logic)
    pipeline_result = {
        "classification_result": {
            "classification": {
                "major_category": "재활용폐기물",
                "middle_category": "플라스틱",
                "minor_category": "PET",
            },
            "situation_tags": ["clean"],
        },
        "disposal_rules": {"rule": "Wash it"},
        "final_answer": {
            "user_answer": "It is recyclable.",
            "insufficiencies": [],  # Empty to trigger reward
        },
    }

    # Act
    # We patch multiple targets:
    # 1. process_waste_classification (to bypass heavy AI logic)
    # 2. get_character_client (to return our mock client)
    with (
        patch(
            "domains.scan.services.scan.process_waste_classification",
            return_value=pipeline_result,
        ) as mock_pipeline,
        patch(
            "domains.scan.services.scan.get_character_client",
            return_value=mock_client,
        ) as mock_get_client,
    ):
        response = await service.classify(payload, user_id)

        # Assert
        # 1. Verify pipeline called
        mock_pipeline.assert_called_once()

        # 2. Verify gRPC client was requested
        mock_get_client.assert_called_once()

        # 3. Verify gRPC method called
        mock_client.get_character_reward.assert_called_once()

        # 4. Verify service response contains mapped reward
        assert response.status == "completed"
        assert response.reward is not None
        assert response.reward.received is True
        assert response.reward.name == "TestChar"
