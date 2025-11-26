#!/bin/bash
# ArgoCD 전체 동기화 스크립트 (kubectl 사용, 로그인 불필요)

set -e

echo "🔄 ArgoCD 전체 동기화 시작..."
echo "환경: ${1:-dev}"
ENV=${1:-dev}

echo ""
echo "📋 동기화할 Applications (sync-wave 순서):"

# sync-wave 순서대로 Applications 나열
APPS=(
    "${ENV}-crds:0"
    "${ENV}-namespaces:2"
    "${ENV}-rbac-storage:3"
    "${ENV}-network-policies:6"
    "${ENV}-secrets-operator:10"
    "${ENV}-secrets-cr:11"
    "${ENV}-alb-controller:15"
    "${ENV}-external-dns:16"
    "${ENV}-monitoring-operator:20"
    "${ENV}-grafana:21"
    "${ENV}-postgresql:27"
    "${ENV}-redis:28"
    "${ENV}-apis-appset:60"
    "${ENV}-ingress:70"
)

for app_info in "${APPS[@]}"; do
    IFS=':' read -r app_name wave <<< "$app_info"
    echo "  [$wave] $app_name"
done

echo ""
read -p "전체 동기화를 시작하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

# 순차적으로 동기화
for app_info in "${APPS[@]}"; do
    IFS=':' read -r app_name wave <<< "$app_info"

    echo ""
    echo "🔄 [$wave] Syncing: $app_name"

    # Application 존재 확인
    if ! kubectl -n argocd get application $app_name &> /dev/null; then
        echo "⚠️  Application $app_name이 존재하지 않습니다. 건너뜀."
        continue
    fi

    # Refresh 트리거 (변경사항 감지)
    echo "📍 Refreshing..."
    kubectl -n argocd annotate application $app_name \
        argocd.argoproj.io/refresh=hard --overwrite

    # Sync 작업 트리거
    echo "🔄 Triggering sync..."
    kubectl -n argocd patch application $app_name \
        --type merge \
        -p '{"metadata":{"annotations":{"argocd.argoproj.io/sync-wave":"'$wave'"}},"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true,"syncOptions":["CreateNamespace=true"]}}}'

    # 잠시 대기 (sync 시작 대기)
    sleep 3

    # Health 확인 (최대 5분)
    echo "⏳ Waiting for $app_name to be healthy..."
    timeout=300
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        status=$(kubectl -n argocd get application $app_name -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
        sync_status=$(kubectl -n argocd get application $app_name -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")

        if [ "$status" = "Healthy" ] && [ "$sync_status" = "Synced" ]; then
            echo "✅ $app_name: Healthy & Synced"
            break
        fi

        echo "   Status: $status, Sync: $sync_status (${elapsed}s/${timeout}s)"
        sleep 10
        elapsed=$((elapsed + 10))
    done

    if [ $elapsed -ge $timeout ]; then
        echo "⚠️  $app_name이 5분 내에 Healthy 상태가 되지 않았습니다."
        read -p "계속 진행하시겠습니까? (y/n): " continue_sync
        if [ "$continue_sync" != "y" ]; then
            echo "동기화 중단"
            exit 1
        fi
    fi

    sleep 2
done

echo ""
echo "🎉 전체 동기화 완료!"
echo ""
echo "📊 최종 상태:"
kubectl -n argocd get applications -l env=$ENV
