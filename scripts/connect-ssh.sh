#!/bin/bash
# SSH를 사용한 빠른 노드 접속 스크립트

NODE_NAME=${1:-master}
REGION=${AWS_REGION:-ap-northeast-2}
SSH_KEY=${SSH_KEY:-~/.ssh/sesacthon}

echo "🔍 $NODE_NAME 인스턴스 Public IP 검색 중..."

# Public IP 조회
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-$NODE_NAME" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].PublicIpAddress" \
  --output text \
  --region $REGION)

if [ -z "$PUBLIC_IP" ]; then
  echo "❌ $NODE_NAME 인스턴스를 찾을 수 없습니다."
  echo ""
  echo "사용법: $0 <node-name>"
  echo "예시:"
  echo "  $0 master     # Master 노드"
  echo "  $0 worker-1   # Worker 1"
  echo "  $0 worker-2   # Worker 2"
  echo "  $0 storage    # Storage 노드"
  exit 1
fi

echo "✅ $NODE_NAME Public IP: $PUBLIC_IP"
echo "🔗 SSH 접속 중..."
echo ""

# SSH 접속
ssh -i $SSH_KEY ubuntu@$PUBLIC_IP


