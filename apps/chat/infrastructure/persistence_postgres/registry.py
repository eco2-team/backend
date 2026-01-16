"""SQLAlchemy Mapper Registry for Chat Domain.

Chat 도메인용 공용 Imperative Mapping Registry.
모든 매핑 파일에서 이 registry와 metadata를 공유합니다.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import registry

from chat.infrastructure.persistence_postgres.constants import CHAT_SCHEMA

# chat 스키마용 공용 메타데이터
metadata = MetaData(schema=CHAT_SCHEMA)
mapper_registry = registry(metadata=metadata)
