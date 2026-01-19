"""gRPC Proto definitions for Image Service client."""

from chat_worker.infrastructure.integrations.image.proto.image_pb2 import (
    UploadBytesRequest,
    UploadBytesResponse,
)
from chat_worker.infrastructure.integrations.image.proto.image_pb2_grpc import (
    ImageServiceStub,
)

__all__ = [
    "UploadBytesRequest",
    "UploadBytesResponse",
    "ImageServiceStub",
]
