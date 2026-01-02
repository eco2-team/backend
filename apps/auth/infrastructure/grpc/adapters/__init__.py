"""gRPC Adapters.

Port 구현체들을 제공합니다.
"""

from apps.auth.infrastructure.grpc.adapters.users_management_gateway_grpc import (
    UsersManagementGatewayGrpc,
)

__all__ = ["UsersManagementGatewayGrpc"]
