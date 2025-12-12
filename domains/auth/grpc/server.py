import grpc
import logging
from domains.auth.grpc.servicer import AuthorizationServicer
from envoy.service.auth.v3 import external_auth_pb2_grpc


async def start_grpc_server(port: int = 9001):
    """
    gRPC 서버를 초기화하고 시작합니다.
    Main Event Loop 내에서 Background Task로 실행될 것을 가정합니다.
    """
    server = grpc.aio.server()
    external_auth_pb2_grpc.add_AuthorizationServicer_to_server(AuthorizationServicer(), server)
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logging.info(f"🚀 Starting gRPC server on {listen_addr}")
    await server.start()

    # 서버 객체를 반환하여 나중에 우아하게 종료(stop)할 수 있게 함
    return server
