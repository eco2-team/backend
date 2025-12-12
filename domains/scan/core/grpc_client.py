import grpc
from domains.scan.core.config import get_settings
from domains.scan.proto import character_pb2_grpc

_channel = None
_stub = None


async def get_character_stub() -> character_pb2_grpc.CharacterServiceStub:
    """
    Returns a singleton gRPC stub for CharacterService.
    Reuses the channel across calls.
    """
    global _channel, _stub

    if _stub is None:
        settings = get_settings()
        target = settings.character_grpc_target
        # gRPC channel is expensive to create, so we reuse it.
        # In production with K8s/Istio, 'insecure_channel' is fine as Istio handles mTLS sidecar-to-sidecar.
        # LB policy is not set here because Istio Sidecar does L7 load balancing.
        _channel = grpc.aio.insecure_channel(target)
        _stub = character_pb2_grpc.CharacterServiceStub(_channel)

    return _stub


async def close_channel():
    """
    Closes the global gRPC channel.
    Should be called on application shutdown.
    """
    global _channel, _stub
    if _channel:
        await _channel.close()
        _channel = None
        _stub = None
