"""Character Service Configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Character 서비스 설정."""

    # Service
    service_name: str = "character-api"
    environment: str = "development"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "character"
    postgres_password: str = "character"
    postgres_db: str = "character"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # gRPC
    grpc_port: int = 50051

    # OpenTelemetry
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    @property
    def database_url(self) -> str:
        """PostgreSQL 연결 URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """Redis 연결 URL."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = {"env_prefix": "", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤을 반환합니다."""
    return Settings()
