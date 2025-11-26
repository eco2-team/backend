#!/bin/bash

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       Auth 서비스 Docker 이미지 변경사항 적용                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

BACKEND_DIR="/Users/mango/workspace/SeSACTHON/backend"

echo "📋 현재 코드 상태 확인..."
echo ""
cd "$BACKEND_DIR/workloads/domains/auth/dev"

echo "=== Kustomize 빌드 결과 (이미지 확인) ==="
kustomize build . | grep "image: docker.io" | head -3
echo ""

echo "🔍 예상 이미지: docker.io/mng990/eco2:auth-api-dev-latest"
echo ""

read -p "클러스터에 적용하시겠습니까? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "⚙️  변경사항 적용 중..."
    echo ""

    # 1. Kustomize로 적용
    echo "1️⃣  kubectl apply -k . 실행..."
    kubectl apply -k .
    echo ""

    # 2. Deployment 재시작
    echo "2️⃣  auth-api Deployment 재시작..."
    kubectl rollout restart deployment auth-api -n auth
    echo ""

    # 3. Job 삭제 (ArgoCD가 재생성)
    echo "3️⃣  auth-db-bootstrap Job 삭제..."
    kubectl delete job auth-db-bootstrap -n auth 2>/dev/null || echo "   (Job이 이미 없거나 삭제됨)"
    echo ""

    echo "✅ 적용 완료!"
    echo ""
    echo "📊 현재 Pod 상태:"
    kubectl get pods -n auth
    echo ""
    echo "🔄 Rollout 상태 확인:"
    kubectl rollout status deployment auth-api -n auth --timeout=60s
    echo ""
    echo "✨ 완료! 새로운 이미지가 적용되었습니다."
else
    echo ""
    echo "❌ 취소되었습니다."
    echo ""
    echo "수동으로 적용하려면 다음 명령어를 실행하세요:"
    echo ""
    echo "  cd $BACKEND_DIR/workloads/domains/auth/dev"
    echo "  kubectl apply -k ."
    echo "  kubectl rollout restart deployment auth-api -n auth"
    echo "  kubectl delete job auth-db-bootstrap -n auth"
fi
