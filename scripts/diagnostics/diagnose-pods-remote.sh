#!/bin/bash
# 로컬에서 Master 노드로 원격 진단 스크립트 실행

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Terraform에서 Master IP 가져오기
cd "$PROJECT_ROOT/terraform"
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 가져올 수 없습니다."
    echo "   Terraform output을 확인하세요: terraform output master_public_ip"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Master 노드로 원격 진단 실행"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Master IP: $MASTER_IP"
echo ""

# SSH 키 경로 확인
SSH_KEY="${HOME}/.ssh/sesacthon"
if [ ! -f "$SSH_KEY" ]; then
    SSH_KEY="${HOME}/.ssh/id_rsa"
    if [ ! -f "$SSH_KEY" ]; then
        echo "❌ SSH 키를 찾을 수 없습니다."
        echo "   $HOME/.ssh/sesacthon 또는 $HOME/.ssh/id_rsa 필요"
        exit 1
    fi
fi

echo "SSH 키: $SSH_KEY"
echo ""
echo "Master 노드에 연결 중..."
echo ""

# 스크립트를 Master 노드로 전송하고 실행
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' < "$SCRIPT_DIR/diagnose-pods.sh"

