"""gRPC client code for users service."""

from apps.auth.infrastructure.grpc import users_pb2, users_pb2_grpc

__all__ = ["users_pb2", "users_pb2_grpc"]
