#!/bin/bash
# PostgreSQL만 빠르게 동기화

set -e

ENV=${1:-dev}
APP_NAME="${ENV}-postgresql"

echo "🔄 PostgreSQL 동기화 시작..."
echo "Application: $APP_NAME"

# kubectl로 직접 annotation 추가 (ArgoCD CLI 없이 가능)
echo "📍 Refresh 트리거..."
kubectl -n argocd annotate application $APP_NAME \
    argocd.argoproj.io/refresh=hard --overwrite

# Sync 트리거
echo "🔄 Sync 트리거..."
kubectl -n argocd patch application $APP_NAME \
    --type merge \
    -p '{"operation":{"initiatedBy":{"username":"manual"},"sync":{"syncStrategy":{"hook":{},"apply":{}}}}}'

echo ""
echo "✅ Sync 트리거 완료!"
echo ""
echo "📊 상태 확인:"
kubectl -n argocd get application $APP_NAME

echo ""
echo "🔍 Pod 상태 모니터링:"
kubectl -n postgres get pods -w
