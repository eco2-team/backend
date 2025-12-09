import pytest

from domains.auth.grpc.servicer import AuthorizationServicer
from domains.auth.grpc.server import start_grpc_server
from envoy.service.auth.v3 import external_auth_pb2


@pytest.mark.asyncio
async def test_grpc_server_starts_and_stops():
    server = await start_grpc_server(port=0)
    await server.stop(grace=None)


def test_authorization_servicer_responses():
    servicer = AuthorizationServicer()

    allow = servicer._allow_request()  # noqa: SLF001
    deny = servicer._deny_request("denied")  # noqa: SLF001

    assert isinstance(allow, external_auth_pb2.CheckResponse)
    assert isinstance(deny, external_auth_pb2.CheckResponse)
    assert deny.status.code != allow.status.code
