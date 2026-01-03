"""Character Worker Configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Character Worker 설정."""

    # Service
    service_name: str = "character-worker"
    environment: str = "development"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "character"
    postgres_password: str = "character"
    postgres_db: str = "character"

    # RabbitMQ
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"

    # Worker
    worker_concurrency: int = 4
    default_character_code: str = "char-eco"

    # Users DB (기본 캐릭터 지급 시 users.user_characters에 저장)
    users_postgres_host: str = "localhost"
    users_postgres_port: int = 5432
    users_postgres_user: str = "users"
    users_postgres_password: str = "users"
    users_postgres_db: str = "users"

    # OpenTelemetry
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    @property
    def database_url(self) -> str:
        """PostgreSQL 연결 URL (sync)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """PostgreSQL 연결 URL (async)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def broker_url(self) -> str:
        """RabbitMQ 브로커 URL."""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )

    @property
    def users_async_database_url(self) -> str:
        """Users DB PostgreSQL 연결 URL (async)."""
        return (
            f"postgresql+asyncpg://{self.users_postgres_user}:{self.users_postgres_password}"
            f"@{self.users_postgres_host}:{self.users_postgres_port}/{self.users_postgres_db}"
        )

    model_config = {"env_prefix": "", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    """설정 싱글톤을 반환합니다."""
    return Settings()
