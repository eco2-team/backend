#!/bin/bash

set -e

# Worker Docker 이미지 빌드 및 GHCR 푸시 스크립트

# 설정
REGISTRY="ghcr.io"
ORGANIZATION="${GITHUB_REPOSITORY_OWNER:-yourorg}"
VERSION="${VERSION:-latest}"

# 컬러 출력
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🐳 Worker Docker Images Build & Push${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 현재 디렉토리 확인
if [[ ! -f "workers/storage_worker.py" ]]; then
    echo "❌ Error: Must run from project root"
    exit 1
fi

# GHCR 로그인 확인
echo -e "${YELLOW}Checking GHCR authentication...${NC}"
if ! docker info | grep -q "$REGISTRY"; then
    echo "❌ Not logged in to GHCR. Please run:"
    echo "   echo \$GITHUB_TOKEN | docker login $REGISTRY -u \$GITHUB_USERNAME --password-stdin"
    exit 1
fi
echo -e "${GREEN}✅ GHCR authenticated${NC}"
echo ""

# 이미지 이름
STORAGE_WORKER_IMAGE="$REGISTRY/$ORGANIZATION/ecoeco-storage-worker:$VERSION"
AI_WORKER_IMAGE="$REGISTRY/$ORGANIZATION/ecoeco-ai-worker:$VERSION"

# Storage Worker 빌드
echo -e "${BLUE}📦 Building Storage Worker...${NC}"
docker build \
    -f workers/Dockerfile.storage \
    -t "$STORAGE_WORKER_IMAGE" \
    --build-arg VERSION="$VERSION" \
    .

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}✅ Storage Worker built: $STORAGE_WORKER_IMAGE${NC}"
else
    echo -e "❌ Failed to build Storage Worker"
    exit 1
fi
echo ""

# AI Worker 빌드
echo -e "${BLUE}📦 Building AI Worker...${NC}"
docker build \
    -f workers/Dockerfile.ai \
    -t "$AI_WORKER_IMAGE" \
    --build-arg VERSION="$VERSION" \
    .

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}✅ AI Worker built: $AI_WORKER_IMAGE${NC}"
else
    echo -e "❌ Failed to build AI Worker"
    exit 1
fi
echo ""

# 이미지 크기 확인
echo -e "${BLUE}📊 Image Sizes:${NC}"
docker images | grep "ecoeco-.*-worker" | grep "$VERSION"
echo ""

# GHCR 푸시
echo -e "${BLUE}🚀 Pushing to GHCR...${NC}"
echo ""

echo -e "${YELLOW}Pushing Storage Worker...${NC}"
docker push "$STORAGE_WORKER_IMAGE"
echo -e "${GREEN}✅ Storage Worker pushed${NC}"
echo ""

echo -e "${YELLOW}Pushing AI Worker...${NC}"
docker push "$AI_WORKER_IMAGE"
echo -e "${GREEN}✅ AI Worker pushed${NC}"
echo ""

# Latest 태그 (선택적)
if [[ "$VERSION" != "latest" ]]; then
    read -p "Tag as 'latest' as well? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        STORAGE_WORKER_LATEST="$REGISTRY/$ORGANIZATION/ecoeco-storage-worker:latest"
        AI_WORKER_LATEST="$REGISTRY/$ORGANIZATION/ecoeco-ai-worker:latest"
        
        docker tag "$STORAGE_WORKER_IMAGE" "$STORAGE_WORKER_LATEST"
        docker tag "$AI_WORKER_IMAGE" "$AI_WORKER_LATEST"
        
        docker push "$STORAGE_WORKER_LATEST"
        docker push "$AI_WORKER_LATEST"
        
        echo -e "${GREEN}✅ Latest tags pushed${NC}"
    fi
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All Worker images built and pushed!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}📦 Pushed Images:${NC}"
echo "  - $STORAGE_WORKER_IMAGE"
echo "  - $AI_WORKER_IMAGE"
echo ""
echo -e "${BLUE}🚀 Next Steps:${NC}"
echo "  1. Update k8s/workers/worker-wal-deployments.yaml with new image tags"
echo "  2. Deploy: kubectl apply -f k8s/workers/worker-wal-deployments.yaml"
echo "  3. Verify: kubectl get pods -l component=worker"
echo ""

