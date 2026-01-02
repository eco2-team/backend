#!/bin/bash
# Proto 파일 컴파일 스크립트
# gRPC Python 코드 생성
#
# 사전 요구사항:
#   brew install protobuf grpc

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/protos"

# grpc_python_plugin 경로 (macOS brew)
GRPC_PLUGIN="${GRPC_PYTHON_PLUGIN:-/opt/homebrew/bin/grpc_python_plugin}"

echo "📦 Proto 컴파일 시작..."

# users.proto → apps/users/infrastructure/grpc/
echo "  → users.proto 컴파일..."
mkdir -p "$PROJECT_ROOT/apps/users/infrastructure/grpc"
protoc -I"$PROTO_DIR" \
    --python_out="$PROJECT_ROOT/apps/users/infrastructure/grpc" \
    --grpc_python_out="$PROJECT_ROOT/apps/users/infrastructure/grpc" \
    --plugin=protoc-gen-grpc_python="$GRPC_PLUGIN" \
    "$PROTO_DIR/users.proto"

# auth 클라이언트용 복사
echo "  → auth 클라이언트용 복사..."
mkdir -p "$PROJECT_ROOT/apps/auth/infrastructure/grpc"
cp "$PROJECT_ROOT/apps/users/infrastructure/grpc/users_pb2.py" \
   "$PROJECT_ROOT/apps/auth/infrastructure/grpc/"
cp "$PROJECT_ROOT/apps/users/infrastructure/grpc/users_pb2_grpc.py" \
   "$PROJECT_ROOT/apps/auth/infrastructure/grpc/"

# __init__.py 생성
cat > "$PROJECT_ROOT/apps/users/infrastructure/grpc/__init__.py" << 'EOF'
"""gRPC generated code for users service."""
from apps.users.infrastructure.grpc import users_pb2, users_pb2_grpc

__all__ = ["users_pb2", "users_pb2_grpc"]
EOF

cat > "$PROJECT_ROOT/apps/auth/infrastructure/grpc/__init__.py" << 'EOF'
"""gRPC client code for users service."""
from apps.auth.infrastructure.grpc import users_pb2, users_pb2_grpc

__all__ = ["users_pb2", "users_pb2_grpc"]
EOF

echo "✅ Proto 컴파일 완료!"
echo "   - apps/users/infrastructure/grpc/"
echo "   - apps/auth/infrastructure/grpc/"
