"""gRPC Proto definitions for Image Service."""

from images.proto.image_pb2 import (
    UploadBytesRequest,
    UploadBytesResponse,
)
from images.proto.image_pb2_grpc import (
    ImageServiceServicer,
    ImageServiceStub,
    add_ImageServiceServicer_to_server,
)

__all__ = [
    "UploadBytesRequest",
    "UploadBytesResponse",
    "ImageServiceServicer",
    "ImageServiceStub",
    "add_ImageServiceServicer_to_server",
]
