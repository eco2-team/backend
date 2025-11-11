#!/bin/bash
# Atlantis Secret 생성 스크립트 (원격 클러스터)
# 사용법: ./create-atlantis-secret.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/terraform"
SSH_KEY="${HOME}/.ssh/id_rsa"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 Atlantis Secret 생성 (원격 클러스터)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Webhook Secret 생성
WEBHOOK_SECRET=$(openssl rand -hex 20)
echo "✅ Webhook Secret 생성: $WEBHOOK_SECRET"
echo ""

# 사용자 입력 받기
read -p "GitHub Personal Access Token (ghp_...): " GITHUB_TOKEN
read -p "AWS Access Key ID: " AWS_ACCESS_KEY_ID
read -sp "AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
echo ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 원격 클러스터에 Secret 생성 중..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform에서 Master IP 가져오기
MASTER_IP=$(cd "$TERRAFORM_DIR" && terraform output -raw master_public_ip 2>/dev/null || echo "")

if [[ -z "$MASTER_IP" ]]; then
    echo "❌ Master 노드 IP를 찾을 수 없습니다"
    echo "   Terraform output을 확인하거나 수동으로 IP를 입력하세요"
    exit 1
fi

echo "📍 Master 노드 IP: $MASTER_IP"
echo ""

# SSH를 통해 원격으로 실행
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@"$MASTER_IP" <<REMOTE_SCRIPT
# Namespace 확인
kubectl get namespace atlantis >/dev/null 2>&1 || kubectl create namespace atlantis

# Secret 생성
kubectl create secret generic atlantis-secrets \
  -n atlantis \
  --from-literal=github-token='$GITHUB_TOKEN' \
  --from-literal=github-webhook-secret='$WEBHOOK_SECRET' \
  --from-literal=aws-access-key-id='$AWS_ACCESS_KEY_ID' \
  --from-literal=aws-secret-access-key='$AWS_SECRET_ACCESS_KEY' \
  --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret 생성 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 생성된 Secret 정보:"
echo "  - Namespace: atlantis"
echo "  - Secret Name: atlantis-secrets"
echo "  - Webhook Secret: $WEBHOOK_SECRET"
REMOTE_SCRIPT

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret 생성 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 생성된 Secret 정보:"
echo "  - Namespace: atlantis"
echo "  - Secret Name: atlantis-secrets"
echo "  - Webhook Secret: $WEBHOOK_SECRET"
echo ""
echo "⚠️  중요: GitHub Webhook 설정 시 위 Webhook Secret을 사용하세요!"
echo ""
echo "📝 다음 단계:"
echo "  1. GitHub Webhook 설정:"
echo "     - Payload URL: https://atlantis.growbin.app/events"
echo "     - Secret: $WEBHOOK_SECRET"
echo "  2. Atlantis 배포:"
echo "     ansible-playbook -i inventory/hosts.ini playbooks/09-atlantis.yml"

