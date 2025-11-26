#!/bin/bash
# ArgoCD 전체 Hard Refresh + Sync (kubectl만 사용)

set -e

ENV=${1:-dev}

echo "🔄 ArgoCD 전체 하드 리프레시 + 동기화"
echo "환경: $ENV"
echo ""

# 모든 Applications 가져오기
APPS=$(kubectl -n argocd get applications -l env=$ENV -o jsonpath='{.items[*].metadata.name}')

if [ -z "$APPS" ]; then
    echo "❌ $ENV 환경의 Applications을 찾을 수 없습니다."
    exit 1
fi

echo "📋 동기화할 Applications:"
for app in $APPS; do
    echo "  - $app"
done

echo ""
read -p "전체 동기화를 시작하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

# 1단계: 모든 Applications Hard Refresh
echo ""
echo "1️⃣  Hard Refresh (변경사항 강제 감지)..."
for app in $APPS; do
    echo "  🔄 $app"
    kubectl -n argocd annotate application $app \
        argocd.argoproj.io/refresh=hard --overwrite
done

echo "✅ Refresh 완료, 5초 대기..."
sleep 5

# 2단계: 모든 Applications Sync 트리거
echo ""
echo "2️⃣  Sync 트리거..."
for app in $APPS; do
    echo "  🚀 $app"
    kubectl -n argocd patch application $app \
        --type merge \
        -p '{"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true}}}' 2>/dev/null || true
done

echo ""
echo "✅ 모든 Applications 동기화 트리거 완료!"
echo ""
echo "📊 현재 상태 (실시간 모니터링):"
echo ""

# 3단계: 상태 모니터링
watch -n 3 "kubectl -n argocd get applications -l env=$ENV -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,MESSAGE:.status.conditions[*].message'"
