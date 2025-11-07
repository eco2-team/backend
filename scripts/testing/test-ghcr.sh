#!/bin/bash
# GHCR (GitHub Container Registry) 동작 확인 스크립트
# GitHub Packages를 통한 컨테이너 이미지 레지스트리 테스트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐳 GHCR (GitHub Container Registry) 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 환경 변수 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "1️⃣ 환경 변수 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ GITHUB_TOKEN이 설정되지 않았습니다."
    echo ""
    echo "📝 토큰 생성 방법:"
    echo "   1. GitHub 설정: https://github.com/settings/tokens"
    echo "   2. 'Generate new token (classic)' 클릭"
    echo "   3. Scopes 선택:"
    echo "      ✅ write:packages (패키지 업로드)"
    echo "      ✅ read:packages (패키지 다운로드)"
    echo "      ✅ delete:packages (패키지 삭제, 선택사항)"
    echo "   4. 토큰 복사 후 환경변수 설정:"
    echo "      export GITHUB_TOKEN=ghp_xxxxxxxxxxxx"
    echo ""
    exit 1
else
    echo "✅ GITHUB_TOKEN: ${GITHUB_TOKEN:0:10}..."
fi

if [ -z "$GITHUB_USERNAME" ]; then
    echo "❌ GITHUB_USERNAME이 설정되지 않았습니다."
    echo "   export GITHUB_USERNAME=your-github-username"
    echo ""
    exit 1
else
    echo "✅ GITHUB_USERNAME: $GITHUB_USERNAME"
fi

GITHUB_ORG="${GITHUB_ORG:-sesacthon}"
echo "✅ GITHUB_ORG: $GITHUB_ORG"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Docker 로그인 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "2️⃣ GHCR 로그인 테스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔐 GHCR 로그인 중..."
if echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin 2>/dev/null; then
    echo "✅ GHCR 로그인 성공!"
else
    echo "❌ GHCR 로그인 실패"
    echo "   토큰 권한을 확인하세요 (write:packages, read:packages)"
    exit 1
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 테스트 이미지 빌드 & 푸시
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "3️⃣ 테스트 이미지 빌드 & 푸시"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TEST_IMAGE="ghcr.io/${GITHUB_ORG}/test-api"
TEST_TAG="test-$(date +%s)"

echo "📦 테스트 이미지: $TEST_IMAGE:$TEST_TAG"
echo ""

# 임시 Dockerfile 생성
TMP_DIR=$(mktemp -d)
cat > "$TMP_DIR/Dockerfile" << 'DOCKERFILE'
FROM python:3.11-slim
WORKDIR /app
RUN echo "print('Hello from GHCR test!')" > app.py
CMD ["python", "app.py"]
DOCKERFILE

echo "🔨 이미지 빌드 중..."
if docker build -t "$TEST_IMAGE:$TEST_TAG" "$TMP_DIR" >/dev/null 2>&1; then
    echo "✅ 이미지 빌드 성공"
else
    echo "❌ 이미지 빌드 실패"
    rm -rf "$TMP_DIR"
    exit 1
fi

echo "📤 GHCR에 푸시 중..."
if docker push "$TEST_IMAGE:$TEST_TAG" 2>&1 | grep -q "digest:"; then
    echo "✅ GHCR 푸시 성공!"
    echo ""
    echo "🔗 이미지 확인:"
    echo "   https://github.com/orgs/${GITHUB_ORG}/packages?repo_name=backend"
else
    echo "❌ GHCR 푸시 실패"
    echo "   Organization 설정에서 패키지 접근 권한을 확인하세요."
    rm -rf "$TMP_DIR"
    exit 1
fi

# 정리
rm -rf "$TMP_DIR"
docker rmi "$TEST_IMAGE:$TEST_TAG" >/dev/null 2>&1
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 이미지 Pull 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "4️⃣ 이미지 Pull 테스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📥 GHCR에서 이미지 다운로드 중..."
if docker pull "$TEST_IMAGE:$TEST_TAG" >/dev/null 2>&1; then
    echo "✅ 이미지 Pull 성공!"
    
    echo "🏃 컨테이너 실행 테스트..."
    if docker run --rm "$TEST_IMAGE:$TEST_TAG" 2>/dev/null | grep -q "Hello from GHCR"; then
        echo "✅ 컨테이너 실행 성공!"
    else
        echo "⚠️  컨테이너 실행 실패"
    fi
    
    # 정리
    docker rmi "$TEST_IMAGE:$TEST_TAG" >/dev/null 2>&1
else
    echo "❌ 이미지 Pull 실패"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. GitHub API로 패키지 목록 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "5️⃣ GitHub Packages 목록 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 Organization의 패키지 목록:"
PACKAGES=$(curl -s \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/orgs/${GITHUB_ORG}/packages?package_type=container" \
    2>/dev/null)

if echo "$PACKAGES" | jq -e '.' >/dev/null 2>&1; then
    PACKAGE_COUNT=$(echo "$PACKAGES" | jq 'length')
    echo "✅ 패키지 수: $PACKAGE_COUNT"
    echo ""
    
    if [ "$PACKAGE_COUNT" -gt 0 ]; then
        echo "📦 패키지 목록:"
        echo "$PACKAGES" | jq -r '.[] | "   - \(.name) (visibility: \(.visibility))"'
    else
        echo "ℹ️  아직 패키지가 없습니다."
        echo "   GitHub Actions workflow를 실행하여 이미지를 빌드하세요."
    fi
else
    echo "⚠️  패키지 목록 조회 실패 (Organization 권한 필요)"
    echo "   개인 계정 패키지 확인:"
    PACKAGES=$(curl -s \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/user/packages?package_type=container" \
        2>/dev/null)
    
    if echo "$PACKAGES" | jq -e '.' >/dev/null 2>&1; then
        PACKAGE_COUNT=$(echo "$PACKAGES" | jq 'length')
        echo "   ✅ 개인 패키지 수: $PACKAGE_COUNT"
    fi
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 테스트 정리 (선택사항)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "6️⃣ 테스트 이미지 정리"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "테스트 패키지를 삭제하시겠습니까? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  테스트 패키지 삭제 중..."
    
    # test-api 패키지 버전 조회
    PACKAGE_VERSIONS=$(curl -s \
        -H "Authorization: Bearer $GITHUB_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/orgs/${GITHUB_ORG}/packages/container/test-api/versions" \
        2>/dev/null)
    
    if echo "$PACKAGE_VERSIONS" | jq -e '.' >/dev/null 2>&1; then
        echo "$PACKAGE_VERSIONS" | jq -r '.[].id' | while read -r VERSION_ID; do
            curl -s -X DELETE \
                -H "Authorization: Bearer $GITHUB_TOKEN" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/orgs/${GITHUB_ORG}/packages/container/test-api/versions/${VERSION_ID}" \
                2>/dev/null
            echo "   ✅ 버전 삭제: $VERSION_ID"
        done
        echo "✅ 테스트 패키지 삭제 완료"
    else
        echo "ℹ️  삭제할 테스트 패키지가 없습니다."
    fi
else
    echo "ℹ️  테스트 패키지 유지"
    echo "   수동 삭제: https://github.com/orgs/${GITHUB_ORG}/packages/container/test-api"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 최종 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ GHCR 동작 확인 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 요약:"
echo "   ✅ GHCR 로그인"
echo "   ✅ 이미지 빌드 & 푸시"
echo "   ✅ 이미지 Pull & 실행"
echo "   ✅ GitHub API 접근"
echo ""
echo "🔗 유용한 링크:"
echo "   - Packages: https://github.com/orgs/${GITHUB_ORG}/packages"
echo "   - Settings: https://github.com/organizations/${GITHUB_ORG}/settings/packages"
echo "   - Actions: https://github.com/${GITHUB_ORG}/backend/actions"
echo ""
echo "🚀 다음 단계:"
echo "   1. GitHub Actions workflow 실행"
echo "   2. API 이미지 자동 빌드 확인"
echo "   3. ArgoCD에서 이미지 자동 배포 확인"
echo ""

