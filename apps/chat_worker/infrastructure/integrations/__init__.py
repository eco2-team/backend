"""Integrations Infrastructure - 외부 서비스 연동 구현체들.

- character/: Character API gRPC 클라이언트
- location/: Location API gRPC 클라이언트

Port 매핑:
- CharacterClientPort → CharacterGrpcClient
- LocationClientPort → LocationGrpcClient
"""

from chat_worker.infrastructure.integrations.character import CharacterGrpcClient
from chat_worker.infrastructure.integrations.location import LocationGrpcClient

__all__ = [
    "CharacterGrpcClient",
    "LocationGrpcClient",
]
