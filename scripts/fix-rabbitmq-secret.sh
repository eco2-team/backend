#!/bin/bash
# RabbitMQ Secret 수정 스크립트
# default_user.conf 키 추가로 Pod 마운트 오류 해결

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 RabbitMQ Secret 수정"
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

# RabbitMQ 비밀번호 가져오기
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-changeme}"
RABBITMQ_USERNAME="${RABBITMQ_USERNAME:-admin}"

echo "🔐 RabbitMQ 사용자 정보:"
echo "  Username: $RABBITMQ_USERNAME"
echo "  Password: ${RABBITMQ_PASSWORD:0:3}***"
echo ""

# Master 노드에서 Secret 수정
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' << EOF
set -e

RABBITMQ_USERNAME="$RABBITMQ_USERNAME"
RABBITMQ_PASSWORD="$RABBITMQ_PASSWORD"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ 기존 Secret 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get secret rabbitmq-default-user -n messaging -o yaml 2>/dev/null || echo "Secret이 없습니다 (새로 생성)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Secret 업데이트 (default_user.conf 추가)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 기존 Secret 가져오기
kubectl get secret rabbitmq-default-user -n messaging -o json > /tmp/rabbitmq-secret.json 2>/dev/null || {
    echo "⚠️  Secret이 없습니다. 새로 생성합니다..."
    
    kubectl create secret generic rabbitmq-default-user \\
        --from-literal=username="\$RABBITMQ_USERNAME" \\
        --from-literal=password="\$RABBITMQ_PASSWORD" \\
        --from-literal=default_user.conf="default_user = \$RABBITMQ_USERNAME
default_pass = \$RABBITMQ_PASSWORD" \\
        -n messaging \\
        --dry-run=client -o yaml | kubectl apply -f -
    
    echo "✅ Secret 생성 완료"
    exit 0
}

# 기존 값 추출
USERNAME=\$(kubectl get secret rabbitmq-default-user -n messaging -o jsonpath='{.data.username}' | base64 -d)
PASSWORD=\$(kubectl get secret rabbitmq-default-user -n messaging -o jsonpath='{.data.password}' | base64 -d)

# Secret 업데이트 (default_user.conf 추가)
kubectl create secret generic rabbitmq-default-user \\
    --from-literal=username="\$USERNAME" \\
    --from-literal=password="\$PASSWORD" \\
    --from-literal=default_user.conf="default_user = \$USERNAME
default_pass = \$PASSWORD" \\
    -n messaging \\
    --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Secret 업데이트 완료"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ RabbitMQ Pod 재시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Pod 삭제 (StatefulSet이 자동으로 재생성)
echo "🗑️  RabbitMQ Pod 삭제 중..."
kubectl delete pod rabbitmq-server-0 -n messaging --wait=false 2>/dev/null || true

echo "⏳ Pod 재시작 대기 중 (최대 2분)..."
for i in {1..24}; do
    POD_STATUS=\$(kubectl get pod rabbitmq-server-0 -n messaging -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
    if [ "\$POD_STATUS" == "Running" ]; then
        echo "✅ RabbitMQ Pod 실행 중"
        break
    elif [ "\$POD_STATUS" == "NotFound" ]; then
        echo "Pod 재생성 대기 중... (\$i/24)"
    else
        echo "Pod 상태: \$POD_STATUS (\$i/24)"
    fi
    sleep 5
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ 최종 상태 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

kubectl get pod rabbitmq-server-0 -n messaging
echo ""

# Pod 이벤트 확인
echo "📋 최근 이벤트:"
kubectl describe pod rabbitmq-server-0 -n messaging | grep -A 10 "Events:" || true
echo ""

EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret 수정 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "다음 명령어로 상태 확인:"
echo "  ./scripts/connect-ssh.sh master"
echo "  kubectl get pod rabbitmq-server-0 -n messaging"
echo "  kubectl describe pod rabbitmq-server-0 -n messaging"

