#!/bin/bash
# Monitoring 상태 확인 스크립트 (Master 노드에서 실행)
# Helm, Prometheus, Grafana 상태 확인

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Monitoring 상태 확인 (원격)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Master IP 가져오기
cd "$TERRAFORM_DIR"
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 가져올 수 없습니다."
    exit 1
fi

# SSH 키 확인
SSH_KEY="${HOME}/.ssh/sesacthon"
if [ ! -f "$SSH_KEY" ]; then
    SSH_KEY="${HOME}/.ssh/id_rsa"
    if [ ! -f "$SSH_KEY" ]; then
        echo "❌ SSH 키를 찾을 수 없습니다."
        exit 1
    fi
fi

echo "📋 Master 노드: $MASTER_IP"
echo "🔑 SSH 키: $SSH_KEY"
echo ""
echo "🔌 Master 노드에 연결 중..."
echo ""

# Master 노드에서 Monitoring 상태 확인
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' << 'REMOTE_CHECK'
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Helm Release 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Helm 설치 확인
if ! which helm &>/dev/null; then
    echo "⚠️  Helm이 설치되지 않았습니다"
    echo ""
else
    echo "📋 Monitoring namespace Helm Release:"
    helm list -n monitoring 2>/dev/null || echo "  (Release 없음)"
    echo ""
    
    echo "📋 ArgoCD namespace Helm Release:"
    helm list -n argocd 2>/dev/null || echo "  (Release 없음)"
    echo ""
    
    echo "📋 kube-system namespace Helm Release:"
    helm list -n kube-system 2>/dev/null || echo "  (Release 없음)"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Prometheus Stack Pod 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get pods -n monitoring -o wide
echo ""

# Pod 상세 상태
PROM_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus --no-headers 2>/dev/null | awk '$3 == "Running" {count++} END {print count+0}' || echo "0")
GRAFANA_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana --no-headers 2>/dev/null | awk '$3 == "Running" {count++} END {print count+0}' || echo "0")
ALERTMANAGER_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager --no-headers 2>/dev/null | awk '$3 == "Running" {count++} END {print count+0}' || echo "0")
NODE_EXPORTER_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=node-exporter --no-headers 2>/dev/null | awk '$3 == "Running" {count++} END {print count+0}' || echo "0")

# 숫자 정규화
PROM_PODS=$(echo "$PROM_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
GRAFANA_PODS=$(echo "$GRAFANA_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
ALERTMANAGER_PODS=$(echo "$ALERTMANAGER_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
NODE_EXPORTER_PODS=$(echo "$NODE_EXPORTER_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')

# 빈 값 체크
[ -z "$PROM_PODS" ] && PROM_PODS="0"
[ -z "$GRAFANA_PODS" ] && GRAFANA_PODS="0"
[ -z "$ALERTMANAGER_PODS" ] && ALERTMANAGER_PODS="0"
[ -z "$NODE_EXPORTER_PODS" ] && NODE_EXPORTER_PODS="0"

echo "📊 Pod 상태 요약:"
echo "  Prometheus: $PROM_PODS Pod"
echo "  Grafana: $GRAFANA_PODS Pod"
echo "  Alertmanager: $ALERTMANAGER_PODS Pod"
echo "  Node Exporter: $NODE_EXPORTER_PODS Pod"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Prometheus StatefulSet 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get statefulset -n monitoring
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Grafana Service 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get svc -n monitoring -l app.kubernetes.io/name=grafana
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ Prometheus Service 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get svc -n monitoring -l app.kubernetes.io/name=prometheus
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ PVC 상태 (Monitoring)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get pvc -n monitoring
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ 최근 이벤트 (실패한 Pod)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FAILED_PODS=$(kubectl get pods -n monitoring --field-selector=status.phase!=Running --no-headers 2>/dev/null | awk '{print $1}' || echo "")
if [ -n "$FAILED_PODS" ]; then
    for pod in $FAILED_PODS; do
        echo "📋 Pod: $pod"
        kubectl describe pod "$pod" -n monitoring | grep -A 5 "Events:" || true
        echo ""
    done
else
    echo "✅ 모든 Pod 정상 실행 중"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ Grafana 접속 정보"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

GRAFANA_SVC=$(kubectl get svc -n monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$GRAFANA_SVC" ]; then
    echo "📍 Service: $GRAFANA_SVC"
    echo "🔗 Port-forward:"
    echo "   kubectl port-forward -n monitoring svc/$GRAFANA_SVC 3000:80"
    echo ""
    echo "🌐 브라우저 접속:"
    echo "   http://localhost:3000"
    echo ""
    echo "🔑 기본 계정:"
    echo "   Username: admin"
    GRAFANA_PASSWORD=$(kubectl get secret -n monitoring prometheus-grafana -o jsonpath='{.data.admin-password}' 2>/dev/null | base64 -d || echo "N/A")
    echo "   Password: $GRAFANA_PASSWORD"
else
    echo "⚠️  Grafana Service를 찾을 수 없습니다"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Monitoring 상태 확인 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REMOTE_CHECK

EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 상태 확인이 성공적으로 완료되었습니다."
else
    echo "⚠️  일부 문제가 발생했을 수 있습니다."
fi

exit $EXIT_CODE

