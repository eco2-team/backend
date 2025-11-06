#!/bin/bash
# 로컬에서 Master 노드로 진단 스크립트 전송 및 실행

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT/terraform"
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 가져올 수 없습니다."
    exit 1
fi

SSH_KEY="${HOME}/.ssh/sesacthon"
[ ! -f "$SSH_KEY" ] && SSH_KEY="${HOME}/.ssh/id_rsa"

echo "Master IP: $MASTER_IP"
echo "SSH 키: $SSH_KEY"
echo ""
echo "Master 노드에서 진단 실행 중..."
echo ""

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' < "$SCRIPT_DIR/diagnose-from-master.sh"
