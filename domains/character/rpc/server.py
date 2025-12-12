import asyncio
import logging
import signal
from concurrent import futures

import grpc
from domains.character.proto import character_pb2_grpc
from domains.character.rpc.v1.character_servicer import CharacterServicer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("character.rpc")


async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    character_pb2_grpc.add_CharacterServiceServicer_to_server(CharacterServicer(), server)
    listen_addr = "[::]:50051"
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
