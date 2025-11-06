#!/bin/bash
# 변경된 서비스를 감지하는 스크립트

set -e

# 기본값
GITHUB_BASE_REF=${GITHUB_BASE_REF:-"HEAD~1"}
GITHUB_SHA=${GITHUB_SHA:-"HEAD"}

echo "🔍 변경된 서비스 감지 중..."
echo "Base: $GITHUB_BASE_REF"
echo "Head: $GITHUB_SHA"
echo ""

# 변경된 파일 목록
CHANGED_FILES=$(git diff --name-only $GITHUB_BASE_REF $GITHUB_SHA)

# 서비스별 변경 여부 확인
check_service() {
    SERVICE=$1
    if echo "$CHANGED_FILES" | grep -q "^services/$SERVICE/"; then
        echo "$SERVICE=true"
        return 0
    else
        echo "$SERVICE=false"
        return 1
    fi
}

# 각 서비스 검사
echo "📦 서비스별 변경 감지 결과:"
check_service "auth"
check_service "users"
check_service "waste"
check_service "recycling"
check_service "locations"

# 공유 라이브러리 변경 시 전체 재빌드
if echo "$CHANGED_FILES" | grep -q "^shared/"; then
    echo ""
    echo "⚠️  공유 라이브러리 변경 감지 - 모든 서비스 재빌드 필요"
    echo "all=true"
fi

# Docker Compose 설정 변경
if echo "$CHANGED_FILES" | grep -q "docker-compose"; then
    echo ""
    echo "⚠️  Docker Compose 설정 변경 감지"
    echo "compose_changed=true"
fi

echo ""
echo "✅ 변경 감지 완료"

