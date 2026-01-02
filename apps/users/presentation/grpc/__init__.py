"""gRPC presentation layer for users domain.

프로토콜:
    - gRPC: auth 도메인에서 호출하는 사용자 관련 서비스

폴더 구조:
    - servicers/: gRPC servicer (thin adapter)
    - server.py: gRPC 서버 부팅 코드
    - users_pb2.py, users_pb2_grpc.py: 생성된 protobuf 파일
"""

from apps.users.presentation.grpc import users_pb2, users_pb2_grpc

__all__ = ["users_pb2", "users_pb2_grpc"]
