"""gRPC Infrastructure.

users 도메인과의 gRPC 통신을 위한 클라이언트와 어댑터를 제공합니다.
"""

from apps.auth.infrastructure.grpc import users_pb2, users_pb2_grpc
from apps.auth.infrastructure.grpc.adapters import UsersManagementGatewayGrpc
from apps.auth.infrastructure.grpc.client import (
    UsersGrpcClient,
    close_users_client,
    get_users_client,
    reset_users_client,
)

__all__ = [
    "users_pb2",
    "users_pb2_grpc",
    "UsersGrpcClient",
    "get_users_client",
    "reset_users_client",
    "close_users_client",
    "UsersManagementGatewayGrpc",
]
