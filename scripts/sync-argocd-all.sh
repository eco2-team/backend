#!/bin/bash
# ArgoCD 전체 동기화 스크립트 (마스터 노드 SSH 접속 후 실행)

set -euo pipefail

ENV=${1:-dev}
NODE_NAME=${SSH_NODE:-master}
REGION=${AWS_REGION:-ap-northeast-2}
SSH_KEY=${SSH_KEY:-~/.ssh/sesacthon.pem}
SSH_OPTS=${SSH_OPTS:-"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"}

echo "🔄 ArgoCD 전체 동기화 (원격 실행)"
echo " - 환경: $ENV"
echo " - 대상 노드: $NODE_NAME"
echo ""

echo "🔍 $NODE_NAME 인스턴스 Public IP 검색 중..."
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-$NODE_NAME" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].PublicIpAddress" \
  --output text \
  --region "$REGION")

if [ -z "$PUBLIC_IP" ]; then
  echo "❌ $NODE_NAME 인스턴스를 찾을 수 없습니다."
  exit 1
fi

echo "✅ $NODE_NAME Public IP: $PUBLIC_IP"
echo "🔗 SSH 접속 후 sync 명령을 실행합니다."
echo ""

ssh -i "$SSH_KEY" $SSH_OPTS ubuntu@"$PUBLIC_IP" "SYNC_ENV=$ENV bash -s" <<'REMOTE'
set -euo pipefail

ENV="${SYNC_ENV:-dev}"
echo "🔄 ArgoCD 전체 동기화 시작..."
echo "환경: $ENV"
echo ""
echo "📋 동기화할 Applications (sync-wave 순서):"

BASE_APPS=(
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
)

APPSETS=(
    "${ENV}-apis:60"
    "${ENV}-ingresses:70"
)

for app_info in "${BASE_APPS[@]}"; do
    IFS=':' read -r app_name wave <<< "$app_info"
    echo "  [$wave] $app_name (Application)"
done

for appset_info in "${APPSETS[@]}"; do
    IFS=':' read -r appset_name wave <<< "$appset_info"
    echo "  [$wave] $appset_name (ApplicationSet)"
done

echo ""
read -p "전체 동기화를 시작하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

for app_info in "${BASE_APPS[@]}"; do
    IFS=':' read -r app_name wave <<< "$app_info"

    echo ""
    echo "🔄 [$wave] Syncing: $app_name"

    if ! kubectl -n argocd get application "$app_name" &> /dev/null; then
        echo "⚠️  Application $app_name이 존재하지 않습니다. 건너뜀."
        continue
    fi

    echo "📍 Refreshing..."
    kubectl -n argocd annotate application "$app_name" \
        argocd.argoproj.io/refresh=hard --overwrite

    echo "🔄 Triggering sync..."
    kubectl -n argocd patch application "$app_name" \
        --type merge \
        -p '{"metadata":{"annotations":{"argocd.argoproj.io/sync-wave":"'$wave'"}},"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true,"syncOptions":["CreateNamespace=true"]}}}'

    sleep 3

    echo "⏳ Waiting for $app_name to be healthy..."
    timeout=300
    elapsed=0
    while [ $elapsed -lt $timeout ]; do
        status=$(kubectl -n argocd get application "$app_name" -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
        sync_status=$(kubectl -n argocd get application "$app_name" -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")

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

# ApplicationSet 처리
for appset_info in "${APPSETS[@]}"; do
    IFS=':' read -r appset_name wave <<< "$appset_info"

    echo ""
    echo "🔄 [$wave] Refreshing ApplicationSet: $appset_name"

    if ! kubectl -n argocd get applicationset "$appset_name" &> /dev/null; then
        echo "⚠️  ApplicationSet $appset_name이 존재하지 않습니다. 건너뜀."
        continue
    fi

    kubectl -n argocd annotate applicationset "$appset_name" \
        argocd.argoproj.io/refresh=hard --overwrite

    sleep 3

    echo "⏳ Waiting for children of $appset_name..."
    children=$(kubectl -n argocd get applications -l applicationset.argoproj.io/name="$appset_name" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')

    for child in $children; do
        echo "   ↳ monitoring $child"
        timeout=300
        elapsed=0
        while [ $elapsed -lt $timeout ]; do
            status=$(kubectl -n argocd get application "$child" -o jsonpath='{.status.health.status}' 2>/dev/null || echo "Unknown")
            sync_status=$(kubectl -n argocd get application "$child" -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")

            if [ "$status" = "Healthy" ] && [ "$sync_status" = "Synced" ]; then
                echo "      ✅ $child: Healthy & Synced"
                break
            fi

            echo "      Status: $status, Sync: $sync_status (${elapsed}s/${timeout}s)"
            sleep 10
            elapsed=$((elapsed + 10))
        done

        if [ $elapsed -ge $timeout ]; then
            echo "      ⚠️  $child가 5분 내에 Healthy 상태가 되지 않았습니다."
            read -p "계속 진행하시겠습니까? (y/n): " continue_child
            if [ "$continue_child" != "y" ]; then
                echo "동기화 중단"
                exit 1
            fi
        fi
    done
done

echo ""
echo "🎉 전체 동기화 완료!"
echo ""
echo "📊 최종 상태:"
kubectl -n argocd get applications -l env=$ENV
REMOTE
