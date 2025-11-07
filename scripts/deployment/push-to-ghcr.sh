#!/bin/bash
# GHCR 이미지 빌드 & 푸시 스크립트

set -e  # 에러 발생 시 중단

OWNER="sesacthon"  # GitHub Organization (소문자)
TAG=${1:-latest}   # 첫 번째 인자로 태그 지정, 기본값 latest

echo "🚀 Building and pushing images to GHCR..."
echo "Owner: $OWNER"
echo "Tag: $TAG"
echo ""

# API 서비스 목록
APIs=("waste-api" "auth-api" "userinfo-api" "location-api" "recycle-info-api" "chat-llm-api")

# 각 API 빌드 & 푸시
for api in "${APIs[@]}"; do
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📦 Building $api..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  
  if [ ! -d "services/$api" ]; then
    echo "⚠️  services/$api not found, skipping..."
    continue
  fi
  
  cd services/$api
  
  # 빌드
  docker build \
    -t ghcr.io/$OWNER/$api:$TAG \
    -t ghcr.io/$OWNER/$api:$(git rev-parse --short HEAD) \
    .
  
  echo "✅ Build complete: ghcr.io/$OWNER/$api:$TAG"
  
  # 푸시
  echo "📤 Pushing to GHCR..."
  docker push ghcr.io/$OWNER/$api:$TAG
  docker push ghcr.io/$OWNER/$api:$(git rev-parse --short HEAD)
  
  echo "✅ Push complete: $api"
  echo ""
  
  cd ../..
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 All images pushed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Pushed images:"
for api in "${APIs[@]}"; do
  echo "  - ghcr.io/$OWNER/$api:$TAG"
  echo "  - ghcr.io/$OWNER/$api:$(git rev-parse --short HEAD)"
done
echo ""
echo "🔗 View packages: https://github.com/orgs/SeSACTHON/packages"

