"""gRPC server for My (User Profile) domain."""

import asyncio
import logging
import signal
from concurrent import futures

import grpc
from domains.my.proto import user_character_pb2_grpc
from domains.my.rpc.v1.user_character_servicer import UserCharacterServicer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("my.rpc")


async def serve():
    """Start the gRPC server."""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    user_character_pb2_grpc.add_UserCharacterServiceServicer_to_server(
        UserCharacterServicer(), server
    )
    listen_addr = "[::]:50052"  # character는 50051, my는 50052
    server.add_insecure_port(listen_addr)
    logger.info(f"Starting gRPC server on {listen_addr}")

    await server.start()

    # Graceful shutdown handler
    stop_event = asyncio.Event()

    def handle_signal(*args):
        logger.info("Received shutdown signal")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await stop_event.wait()
    logger.info("Stopping gRPC server...")
    await server.stop(grace=5)
    logger.info("gRPC server stopped.")


if __name__ == "__main__":
    asyncio.run(serve())
