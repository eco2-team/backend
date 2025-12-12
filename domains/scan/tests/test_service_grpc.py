import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from domains.scan.schemas.scan import ClassificationRequest
from domains.scan.services.scan import ScanService
from domains.scan.core.config import Settings

# Add domain paths for import resolution
sys.path.append(str(Path(__file__).resolve().parents[2]))


@pytest.mark.asyncio
async def test_scan_service_grpc_call():
    # Arrange
    user_id = uuid4()
    mock_settings = Settings(
        reward_feature_enabled=True,
        character_api_timeout_seconds=5.0,
    )
    service = ScanService(settings=mock_settings)

    # Mock payload
    payload = ClassificationRequest(
        image_url="http://example.com/test.jpg",
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

    # Mock stub
    mock_stub = AsyncMock()
    mock_stub.GetCharacterReward.return_value = mock_grpc_response

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
    # 2. get_character_stub (to return our mock stub)
    with (
        patch(
            "domains.scan.services.scan.process_waste_classification",
            return_value=pipeline_result,
        ) as mock_pipeline,
        patch(
            "domains.scan.services.scan.get_character_stub",
            return_value=mock_stub,
        ) as mock_get_stub,
    ):
        response = await service.classify(payload, user_id)

        # Assert
        # 1. Verify pipeline called
        mock_pipeline.assert_called_once()

        # 2. Verify gRPC stub was requested
        mock_get_stub.assert_called_once()

        # 3. Verify gRPC method called with correct arguments
        mock_stub.GetCharacterReward.assert_called_once()
        call_args = mock_stub.GetCharacterReward.call_args
        grpc_request = call_args[0][0]  # First positional arg is the request message

        assert grpc_request.source == "scan"
        assert grpc_request.user_id == str(user_id)
        assert grpc_request.classification.major_category == "재활용폐기물"
        assert grpc_request.classification.middle_category == "플라스틱"

        # 4. Verify service response contains mapped reward
        assert response.status == "completed"
        assert response.reward is not None
        assert response.reward.received is True
        assert response.reward.name == "TestChar"
