#!/bin/bash
# etcd 상태 확인 스크립트 (Master 노드에서 실행)
# etcd 인증서 경로 자동 감지 및 health check

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 etcd 상태 확인 (원격)"
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

# Master 노드에서 etcd 상태 확인
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' << 'REMOTE_CHECK'
set +e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ etcd 인증서 경로 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# kubeadm 기본 경로
K8S_PKI="/etc/kubernetes/pki"
ETCD_PKI="$K8S_PKI/etcd"

# 대체 경로들
ALTERNATIVE_PATHS=(
    "/etc/etcd/pki"
    "/var/lib/etcd/pki"
)

echo "📋 확인할 경로:"
echo "  1. $ETCD_PKI (kubeadm 기본)"
for path in "${ALTERNATIVE_PATHS[@]}"; do
    echo "  - $path"
done
echo ""

# 인증서 파일 찾기
CA_CERT=""
SERVER_CERT=""
SERVER_KEY=""

# kubeadm 기본 경로 확인
if [ -f "$ETCD_PKI/ca.crt" ] && [ -f "$ETCD_PKI/server.crt" ] && [ -f "$ETCD_PKI/server.key" ]; then
    CA_CERT="$ETCD_PKI/ca.crt"
    SERVER_CERT="$ETCD_PKI/server.crt"
    SERVER_KEY="$ETCD_PKI/server.key"
    echo "✅ kubeadm 기본 경로에서 인증서 발견: $ETCD_PKI"
elif [ -f "$K8S_PKI/etcd/ca.crt" ] && [ -f "$K8S_PKI/etcd/server.crt" ] && [ -f "$K8S_PKI/etcd/server.key" ]; then
    CA_CERT="$K8S_PKI/etcd/ca.crt"
    SERVER_CERT="$K8S_PKI/etcd/server.crt"
    SERVER_KEY="$K8S_PKI/etcd/server.key"
    echo "✅ 인증서 발견: $K8S_PKI/etcd"
else
    # 대체 경로 확인
    FOUND=false
    for path in "${ALTERNATIVE_PATHS[@]}"; do
        if [ -f "$path/ca.crt" ] && [ -f "$path/server.crt" ] && [ -f "$path/server.key" ]; then
            CA_CERT="$path/ca.crt"
            SERVER_CERT="$path/server.crt"
            SERVER_KEY="$path/server.key"
            echo "✅ 대체 경로에서 인증서 발견: $path"
            FOUND=true
            break
        fi
    done
    
    if [ "$FOUND" = false ]; then
        echo "⚠️  etcd 인증서를 찾을 수 없습니다."
        echo ""
        echo "📋 파일 시스템 검색:"
        find /etc -name "ca.crt" -path "*/etcd/*" 2>/dev/null | head -5 || echo "  (검색 결과 없음)"
        echo ""
        echo "📋 Kubernetes 인증서 목록:"
        ls -la "$K8S_PKI/" 2>/dev/null | head -10 || echo "  ($K8S_PKI 경로 없음)"
        exit 1
    fi
fi

echo ""
echo "📋 인증서 파일:"
echo "  CA: $CA_CERT"
echo "  Server Cert: $SERVER_CERT"
echo "  Server Key: $SERVER_KEY"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ etcd Pod/컨테이너 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# etcd가 Pod로 실행되는지 확인 (외부 etcd가 아닌 경우)
ETCD_POD=$(kubectl get pods -n kube-system -l component=etcd --no-headers 2>/dev/null | awk '{print $1}' | head -1 || echo "")

if [ -n "$ETCD_POD" ]; then
    echo "✅ etcd Pod 발견: $ETCD_POD"
    echo ""
    echo "📋 Pod 상태:"
    kubectl get pods -n kube-system -l component=etcd
    echo ""
    echo "📋 Pod 상세:"
    kubectl describe pod "$ETCD_POD" -n kube-system | grep -A 10 "Status:" || true
    echo ""
else
    echo "ℹ️  etcd Pod 없음 (Master 노드의 static Pod 또는 외부 etcd일 수 있음)"
    echo ""
    echo "📋 Master 노드의 etcd 프로세스 확인:"
    sudo ps aux | grep etcd | grep -v grep || echo "  (프로세스 없음)"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ etcd Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# etcdctl 설치 확인
if ! which etcdctl &>/dev/null; then
    echo "⚠️  etcdctl이 설치되지 않았습니다."
    echo ""
    echo "📦 설치 방법:"
    echo "  sudo apt-get update"
    echo "  sudo apt-get install -y etcd-client"
    echo ""
    echo "또는:"
    echo "  ETCD_VER=v3.5.9"
    echo "  curl -L https://github.com/etcd-io/etcd/releases/download/\${ETCD_VER}/etcd-\${ETCD_VER}-linux-amd64.tar.gz -o /tmp/etcd-\${ETCD_VER}-linux-amd64.tar.gz"
    echo "  tar xzvf /tmp/etcd-\${ETCD_VER}-linux-amd64.tar.gz -C /tmp"
    echo "  sudo mv /tmp/etcd-\${ETCD_VER}-linux-amd64/etcdctl /usr/local/bin/"
    echo ""
    exit 1
fi

# etcd endpoint 확인
ETCD_ENDPOINTS="https://127.0.0.1:2379"

echo "🔍 etcd endpoint: $ETCD_ENDPOINTS"
echo ""

# Health check 실행
echo "📋 Health Check 실행 중..."
ETCD_HEALTH=$(sudo ETCDCTL_API=3 etcdctl endpoint health \
    --endpoints="$ETCD_ENDPOINTS" \
    --cacert="$CA_CERT" \
    --cert="$SERVER_CERT" \
    --key="$SERVER_KEY" \
    2>&1)

ETCD_EXIT_CODE=$?

if [ $ETCD_EXIT_CODE -eq 0 ] && echo "$ETCD_HEALTH" | grep -q "is healthy"; then
    echo "✅ etcd: healthy"
    echo ""
    echo "$ETCD_HEALTH"
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "4️⃣ etcd 상태 상세 정보"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    echo "📋 etcd endpoint status:"
    sudo ETCDCTL_API=3 etcdctl endpoint status \
        --endpoints="$ETCD_ENDPOINTS" \
        --cacert="$CA_CERT" \
        --cert="$SERVER_CERT" \
        --key="$SERVER_KEY" \
        --write-out=table 2>&1 || echo "  (실패)"
    echo ""
    
    echo "📋 etcd member list:"
    sudo ETCDCTL_API=3 etcdctl member list \
        --endpoints="$ETCD_ENDPOINTS" \
        --cacert="$CA_CERT" \
        --cert="$SERVER_CERT" \
        --key="$SERVER_KEY" \
        --write-out=table 2>&1 || echo "  (실패)"
    echo ""
    
else
    echo "⚠️  etcd: 상태 확인 실패 또는 비정상"
    echo ""
    echo "오류 메시지:"
    echo "$ETCD_HEALTH"
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔧 문제 해결 방법"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    echo "1. etcd Pod/프로세스 확인:"
    if [ -n "$ETCD_POD" ]; then
        echo "   kubectl logs $ETCD_POD -n kube-system"
        echo "   kubectl describe pod $ETCD_POD -n kube-system"
    else
        echo "   sudo systemctl status etcd"
        echo "   sudo journalctl -u etcd -n 50"
    fi
    echo ""
    
    echo "2. 인증서 경로 확인:"
    echo "   ls -la $ETCD_PKI/"
    echo "   ls -la $K8S_PKI/"
    echo ""
    
    echo "3. etcd endpoint 접근 확인:"
    echo "   sudo netstat -tlnp | grep 2379"
    echo "   sudo ss -tlnp | grep 2379"
    echo ""
    
    echo "4. etcd 로그 확인:"
    if [ -n "$ETCD_POD" ]; then
        echo "   kubectl logs $ETCD_POD -n kube-system --tail=50"
    else
        echo "   sudo journalctl -u etcd -n 100 --no-pager"
        echo "   sudo tail -f /var/log/etcd.log"
    fi
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ etcd 상태 확인 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REMOTE_CHECK

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ etcd 상태 확인이 완료되었습니다."
else
    echo "⚠️  etcd 상태 확인 중 문제가 발생했습니다."
fi

exit $EXIT_CODE

