#!/usr/bin/env python3
"""Scan API E2E Test Script (Smoke Test).

DB 없이 핵심 모듈만 테스트합니다.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Environment setup
os.environ["SCAN_AUTH_DISABLED"] = "true"
os.environ["SCAN_REWARD_FEATURE_ENABLED"] = "false"
os.environ["OTEL_ENABLED"] = "false"


async def test_app_creation():
    """앱 생성 및 Health 엔드포인트 테스트."""
    from httpx import ASGITransport, AsyncClient
    from domains.scan.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        print("\n[1] App Creation & Health Check...")
        response = await client.get("/health")
        print(f"    Status: {response.status_code}")
        assert response.status_code == 200
        print("    ✅ App creation passed")


async def test_pipeline_direct():
    """파이프라인 직접 호출 테스트 (DB 우회)."""
    from domains._shared.waste_pipeline import process_waste_classification

    print("\n[2] Pipeline Direct Call (GPT API)...")
    image_url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
    print(f"    Image URL: {image_url}")

    try:
        result = await asyncio.to_thread(
            process_waste_classification,
            "",  # user_input_text
            image_url,
            save_result=False,
            verbose=False,
        )
        print(f"    Result type: {type(result).__name__}")

        if isinstance(result, dict):
            cls_result = result.get("classification_result", {})
            cls = cls_result.get("classification", {})
            print(f"    Major: {cls.get('major_category')}")
            print(f"    Middle: {cls.get('middle_category')}")
            print("    ✅ Pipeline direct call passed")
            return True
        else:
            print(f"    ⚠️ Unexpected result: {str(result)[:100]}")
            return False
    except Exception as e:
        print(f"    ❌ Pipeline failed: {e}")
        return False


async def test_grpc_client_init():
    """gRPC Client 초기화 테스트."""
    print("\n[3] gRPC Client Initialization...")
    from domains.scan.core.grpc_client import CharacterGrpcClient
    from domains.scan.core.config import get_settings

    settings = get_settings()
    client = CharacterGrpcClient(settings)

    print(f"    Target: {client.target}")
    print(f"    Circuit State: {client.circuit_state}")
    print(f"    Max Retries: {client.max_retries}")
    print("    ✅ gRPC client init passed")


async def test_validators():
    """URL Validator 테스트."""
    print("\n[4] URL Validators...")
    from domains.scan.core.validators import ImageUrlValidator
    from domains.scan.core.config import get_settings

    settings = get_settings()
    validator = ImageUrlValidator(settings)

    # Valid URL
    valid_url = "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg"
    result = validator.validate(valid_url)
    assert result.valid, f"Valid URL rejected: {result.message}"
    print(f"    Valid URL: ✅")

    # Invalid URL (HTTP)
    invalid_url = "http://evil.com/malware.jpg"
    result = validator.validate(invalid_url)
    assert not result.valid
    print(f"    Invalid URL blocked: ✅")

    print("    ✅ Validators passed")


async def main():
    print("=" * 60)
    print("Scan API Smoke Test (DB-less)")
    print("=" * 60)

    await test_app_creation()
    await test_grpc_client_init()
    await test_validators()

    # GPT API 테스트는 선택적
    if os.environ.get("OPENAI_API_KEY"):
        success = await test_pipeline_direct()
        if not success:
            print("\n⚠️ Pipeline test failed but other tests passed")
    else:
        print("\n[2] Pipeline Test: SKIPPED (no OPENAI_API_KEY)")

    print("\n" + "=" * 60)
    print("Smoke Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
