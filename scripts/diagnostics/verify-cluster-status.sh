#!/bin/bash
# 클러스터 상태 상세 확인 스크립트 (Master 노드에서 실행)
# check-cluster-health.sh에서 경고가 나온 항목들을 상세히 확인

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 클러스터 상태 상세 확인"
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

# Master 노드에서 상세 확인
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' << 'REMOTE_CHECK'
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ RabbitMQ Pod 상세 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 Pod 상태:"
kubectl get pods -n messaging -o wide
echo ""

echo "📋 Pod 라벨:"
kubectl get pods -n messaging --show-labels | grep rabbitmq || echo "  (없음)"
echo ""

echo "📋 RabbitmqCluster CR:"
kubectl get rabbitmqcluster -n messaging
echo ""

echo "📋 StatefulSet:"
kubectl get statefulset -n messaging
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Helm Release 상세 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if which helm &>/dev/null; then
    echo "📋 Monitoring namespace:"
    helm list -n monitoring -o table || echo "  (Release 없음)"
    echo ""
    
    echo "📋 ArgoCD namespace:"
    helm list -n argocd -o table || echo "  (Release 없음)"
    echo ""
    
    echo "📋 helm status 결과 (Prometheus):"
    helm status prometheus -n monitoring 2>/dev/null | head -20 || echo "  (실패)"
    echo ""
    
    echo "📋 helm status 결과 (ArgoCD):"
    helm status argocd -n argocd 2>/dev/null | head -20 || echo "  (실패)"
    echo ""
else
    echo "⚠️  Helm이 설치되지 않았습니다"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Monitoring Pod 상세"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 모든 Pod:"
kubectl get pods -n monitoring -o wide
echo ""

echo "📋 Prometheus Pod:"
kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
echo ""

echo "📋 Grafana Pod:"
kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana
echo ""

echo "📋 Node Exporter Pod:"
kubectl get pods -n monitoring -l app.kubernetes.io/name=node-exporter
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ ArgoCD Pod 상세"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 모든 Pod:"
kubectl get pods -n argocd -o wide
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ etcd 상태 상세 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 etcd 인증서 경로 확인:"
if [ -d "/etc/kubernetes/pki/etcd" ]; then
    ls -la /etc/kubernetes/pki/etcd/ | grep -E "ca.crt|server.crt|server.key" || echo "  (인증서 파일 확인 중...)"
    echo ""
    
    echo "📋 etcd health check (대체 경로):"
    sudo ETCDCTL_API=3 etcdctl endpoint health \
        --endpoints=https://127.0.0.1:2379 \
        --cacert=/etc/kubernetes/pki/etcd/ca.crt \
        --cert=/etc/kubernetes/pki/etcd/server.crt \
        --key=/etc/kubernetes/pki/etcd/server.key 2>&1 || echo "  (실패 - 인증서 경로 확인 필요)"
else
    echo "  ⚠️  /etc/kubernetes/pki/etcd 경로가 없습니다"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 상세 확인 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REMOTE_CHECK

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 상세 확인이 완료되었습니다."
else
    echo "⚠️  일부 확인 중 문제가 발생했을 수 있습니다."
fi

exit $EXIT_CODE

