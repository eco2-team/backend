#!/bin/bash
set -e

# SSH 키 경로 확인 (환경에 맞게 수정 필요)
SSH_KEY=${SSH_KEY:-~/.ssh/sesacthon.pem}
REGION=${AWS_REGION:-ap-northeast-2}
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

echo "🔍 Master 노드 IP 검색 중..."

# Public IP 조회 (connect-ssh.sh 로직 차용)
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-master" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].PublicIpAddress" \
  --output text \
  --region $REGION)

if [ -z "$PUBLIC_IP" ]; then
    echo "❌ Master 노드를 찾을 수 없습니다."
    exit 1
fi

echo "✅ Master IP: $PUBLIC_IP"
echo "🚀 접속하여 키 교체 작업 시작..."

# 원격 실행
ssh -i "$SSH_KEY" $SSH_OPTS ubuntu@"$PUBLIC_IP" "bash -s" <<'EOF'
set -e

echo "1️⃣  [Remote] Deleting Secrets to trigger External Secrets sync..."
kubectl delete secret scan-secret -n scan --ignore-not-found
kubectl delete secret chat-secret -n chat --ignore-not-found

echo "⏳ [Remote] Waiting 5s for recreation..."
sleep 5

echo "2️⃣  [Remote] Verifying new key..."
NEW_KEY=$(kubectl get secret scan-secret -n scan -o jsonpath="{.data.OPENAI_API_KEY}" | base64 -d)

if [ -z "$NEW_KEY" ]; then
    echo "❌ [Remote] Error: Secret was not recreated."
    exit 1
fi

# 키 끝 4자리 확인
SUFFIX="${NEW_KEY: -4}"
echo "   🔑 Current Key Suffix: ...$SUFFIX"

echo "3️⃣  [Remote] Restarting Deployments..."
kubectl rollout restart deployment/scan-api -n scan
kubectl rollout restart deployment/chat-api -n chat

echo "⏳ [Remote] Waiting for rollout..."
kubectl rollout status deployment/scan-api -n scan --timeout=60s

echo "✨ [Remote] Success! Services are running with the new key."
EOF
