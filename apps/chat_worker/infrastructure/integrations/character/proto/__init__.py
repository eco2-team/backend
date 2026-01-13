"""Character Proto - gRPC 생성 코드."""

from chat_worker.infrastructure.integrations.character.proto import character_pb2
from chat_worker.infrastructure.integrations.character.proto import (
    character_pb2_grpc,
)

__all__ = ["character_pb2", "character_pb2_grpc"]
