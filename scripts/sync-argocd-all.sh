#!/bin/bash
# ArgoCD 전체 동기화 스크립트 (sync-wave 순서대로)

set -e

echo "🔄 ArgoCD 전체 동기화 시작..."
echo "환경: ${1:-dev}"
ENV=${1:-dev}

# ArgoCD CLI 설치 확인
if ! command -v argocd &> /dev/null; then
    echo "❌ ArgoCD CLI가 설치되어 있지 않습니다."
    echo "설치: brew install argocd"
    exit 1
fi

# ArgoCD 로그인 (필요시)
read -p "ArgoCD에 로그인이 필요합니까? (y/n): " login
if [ "$login" = "y" ]; then
    read -p "ArgoCD 서버 주소: " argocd_server
    argocd login $argocd_server
fi

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
    if ! argocd app get $app_name &> /dev/null; then
        echo "⚠️  Application $app_name이 존재하지 않습니다. 건너뜀."
        continue
    fi
    
    # Sync 실행
    argocd app sync $app_name --prune --retry-limit 3
    
    # Health 확인 (타임아웃: 5분)
    echo "⏳ Waiting for $app_name to be healthy..."
    argocd app wait $app_name --health --timeout 300 || {
        echo "⚠️  $app_name이 5분 내에 Healthy 상태가 되지 않았습니다."
        read -p "계속 진행하시겠습니까? (y/n): " continue_sync
        if [ "$continue_sync" != "y" ]; then
            echo "동기화 중단"
            exit 1
        fi
    }
    
    echo "✅ $app_name 동기화 완료"
    sleep 2
done

echo ""
echo "🎉 전체 동기화 완료!"
echo ""
echo "📊 최종 상태:"
argocd app list --selector env=$ENV

