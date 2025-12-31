#!/bin/bash
# ============================================================================
# Auth Service Docker Test Runner
#
# Usage:
#   ./scripts/test.sh          # 전체 테스트
#   ./scripts/test.sh unit     # 유닛 테스트만
#   ./scripts/test.sh coverage # 커버리지 포함
#   ./scripts/test.sh build    # 이미지 빌드만
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTH_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$AUTH_DIR/docker-compose.test.yml"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Auth Service Docker Tests${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
}

build_image() {
    echo -e "${YELLOW}📦 Building test image...${NC}"
    docker-compose -f "$COMPOSE_FILE" build test
    echo -e "${GREEN}✅ Build complete${NC}"
}

run_all_tests() {
    echo -e "${YELLOW}🧪 Running all tests...${NC}"
    docker-compose -f "$COMPOSE_FILE" run --rm test
}

run_unit_tests() {
    echo -e "${YELLOW}🧪 Running unit tests...${NC}"
    docker-compose -f "$COMPOSE_FILE" run --rm test-unit
}

run_coverage() {
    echo -e "${YELLOW}📊 Running tests with coverage...${NC}"
    docker-compose -f "$COMPOSE_FILE" run --rm test-coverage
    echo -e "${GREEN}📁 Coverage report: domains/auth/coverage/html/index.html${NC}"
}

cleanup() {
    echo -e "${YELLOW}🧹 Cleaning up containers...${NC}"
    docker-compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
}

# 종료 시 정리
trap cleanup EXIT

print_header

case "${1:-all}" in
    build)
        build_image
        ;;
    unit)
        build_image
        run_unit_tests
        ;;
    coverage)
        build_image
        run_coverage
        ;;
    all|*)
        build_image
        run_all_tests
        ;;
esac

echo ""
echo -e "${GREEN}✅ Done!${NC}"
