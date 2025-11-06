"""
FastAPI Health Check Module

Kubernetes liveness/readiness probe 엔드포인트 제공

사용법:
    from app.health import setup_health_checks

    app = FastAPI()
    setup_health_checks(app, service_name="waste-api")
"""

import time
from typing import Callable, Dict

from fastapi import FastAPI, HTTPException


class HealthChecker:
    """Health check 상태 관리"""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.startup_time = time.time()
        self.readiness_checks: Dict[str, Callable] = {}
        self._is_shutting_down = False

    def add_readiness_check(self, name: str, check_func: Callable):
        """
        Readiness check 함수 등록

        Args:
            name: Check 이름 (예: "database", "redis")
            check_func: async 함수, True/False 반환
        """
        self.readiness_checks[name] = check_func

    async def check_liveness(self) -> Dict:
        """
        Liveness probe - 프로세스가 살아있는지 확인

        Returns:
            Dict: {status, service, uptime}
        """
        uptime = int(time.time() - self.startup_time)

        if self._is_shutting_down:
            raise HTTPException(status_code=503, detail="Service is shutting down")

        return {"status": "healthy", "service": self.service_name, "uptime_seconds": uptime}

    async def check_readiness(self) -> Dict:
        """
        Readiness probe - 트래픽을 받을 준비가 되었는지 확인

        Returns:
            Dict: {status, service, checks}
        """
        if self._is_shutting_down:
            raise HTTPException(status_code=503, detail="Service is shutting down")

        checks = {}
        all_ready = True

        for name, check_func in self.readiness_checks.items():
            try:
                result = await check_func()
                checks[name] = "ready" if result else "not_ready"
                if not result:
                    all_ready = False
            except Exception as e:
                checks[name] = f"error: {str(e)}"
                all_ready = False

        if not all_ready:
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "service": self.service_name, "checks": checks},
            )

        return {
            "status": "ready",
            "service": self.service_name,
            "checks": checks if checks else {"no_checks": "ready"},
        }

    def shutdown(self):
        """Graceful shutdown 시작"""
        self._is_shutting_down = True


def setup_health_checks(app: FastAPI, service_name: str) -> HealthChecker:
    """
    FastAPI 앱에 health check 엔드포인트 추가

    Args:
        app: FastAPI 애플리케이션
        service_name: 서비스 이름

    Returns:
        HealthChecker 인스턴스 (readiness check 등록용)
    """
    health_checker = HealthChecker(service_name)

    @app.get("/health", tags=["health"])
    async def health():
        """
        Liveness probe endpoint

        Kubernetes가 이 엔드포인트로 프로세스 상태 확인
        실패 시 Pod 재시작
        """
        return await health_checker.check_liveness()

    @app.get("/ready", tags=["health"])
    async def ready():
        """
        Readiness probe endpoint

        Kubernetes가 이 엔드포인트로 트래픽 수신 준비 확인
        실패 시 Service에서 제거 (트래픽 차단)
        """
        return await health_checker.check_readiness()

    @app.on_event("shutdown")
    async def shutdown_event():
        """Graceful shutdown"""
        health_checker.shutdown()

    return health_checker


# 공통 Readiness Check 함수들


async def check_postgres(host: str, port: int, database: str, user: str, password: str) -> bool:
    """PostgreSQL 연결 확인"""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=host, port=port, database=database, user=user, password=password, timeout=3
        )
        await conn.close()
        return True
    except Exception:
        return False


async def check_redis(host: str, port: int) -> bool:
    """Redis 연결 확인"""
    try:
        import aioredis

        redis = await aioredis.create_redis_pool(f"redis://{host}:{port}", timeout=3)
        await redis.ping()
        redis.close()
        await redis.wait_closed()
        return True
    except Exception:
        return False


async def check_rabbitmq(host: str, port: int, user: str, password: str) -> bool:
    """RabbitMQ 연결 확인"""
    try:
        import aio_pika

        connection = await aio_pika.connect_robust(
            f"amqp://{user}:{password}@{host}:{port}/", timeout=3
        )
        await connection.close()
        return True
    except Exception:
        return False


async def check_s3(bucket: str, region: str) -> bool:
    """S3 버킷 접근 확인"""
    try:
        import aioboto3

        session = aioboto3.Session()
        async with session.client("s3", region_name=region) as s3:
            await s3.head_bucket(Bucket=bucket)
        return True
    except Exception:
        return False
