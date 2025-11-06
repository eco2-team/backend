"""
Waste API Service

폐기물 분류 API 서비스
"""

import os

from fastapi import FastAPI

from app.health import (
    check_postgres,
    check_redis,
    check_s3,
    setup_health_checks,
)

app = FastAPI(title="Waste API", description="폐기물 분류 및 분석 API", version="1.0.0")

# Health Check 설정
health_checker = setup_health_checks(app, service_name="waste-api")


# Readiness Checks 등록
@app.on_event("startup")
async def startup_event():
    """서비스 시작 시 readiness check 등록"""

    # PostgreSQL check
    health_checker.add_readiness_check(
        "database",
        lambda: check_postgres(
            host=os.getenv("POSTGRES_HOST", "k8s-postgresql"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "growbin_waste"),
            user=os.getenv("POSTGRES_USER", "growbin"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        ),
    )

    # Redis check
    health_checker.add_readiness_check(
        "cache",
        lambda: check_redis(
            host=os.getenv("REDIS_HOST", "k8s-redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
        ),
    )

    # S3 check
    health_checker.add_readiness_check(
        "storage",
        lambda: check_s3(
            bucket=os.getenv("S3_BUCKET", "growbin-images"),
            region=os.getenv("AWS_REGION", "ap-northeast-2"),
        ),
    )


# Business Logic Endpoints


@app.get("/api/v1/waste/categories")
async def get_waste_categories():
    """폐기물 카테고리 목록"""
    return {
        "categories": [
            {"id": 1, "name": "plastic", "display_name": "플라스틱"},
            {"id": 2, "name": "paper", "display_name": "종이"},
            {"id": 3, "name": "glass", "display_name": "유리"},
            {"id": 4, "name": "metal", "display_name": "금속"},
            {"id": 5, "name": "general", "display_name": "일반쓰레기"},
        ]
    }


@app.post("/api/v1/waste/classify")
async def classify_waste(image_url: str):
    """
    폐기물 이미지 분류

    Args:
        image_url: 분류할 이미지 URL

    Returns:
        분류 결과 (category, confidence, disposal_method)
    """
    return {
        "task_id": "example-task-id",
        "status": "pending",
        "message": "분류 작업이 시작되었습니다",
    }


@app.get("/api/v1/waste/task/{task_id}")
async def get_classification_result(task_id: str):
    """
    분류 작업 결과 조회

    Args:
        task_id: 작업 ID

    Returns:
        작업 상태 및 결과
    """
    # TODO: Celery 결과 조회
    return {
        "task_id": task_id,
        "status": "completed",
        "result": {
            "category": "plastic",
            "confidence": 0.95,
            "disposal_method": "플라스틱 전용 수거함에 배출",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
