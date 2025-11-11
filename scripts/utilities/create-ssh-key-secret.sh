#!/bin/bash
# Phase 3: SSH Key Secret 생성 스크립트
# ArgoCD Hooks에서 Ansible이 SSH로 접속하기 위한 Secret 생성

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECRET_NAME="k8s-cluster-ssh-key"
NAMESPACE="argocd"
SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_rsa}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSH Key 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo "❌ SSH Key not found: $SSH_KEY_PATH"
    echo ""
    echo "💡 해결 방법:"
    echo "   1. SSH Key 생성: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa"
    echo "   2. 또는 기존 Key 경로 지정: export SSH_KEY_PATH=/path/to/key"
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# kubectl 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found"
    echo "   Please install kubectl first"
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Namespace 확인/생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo "📝 Creating namespace: $NAMESPACE"
    kubectl create namespace "$NAMESPACE"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Secret 생성/업데이트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 Creating SSH Key Secret for ArgoCD Hooks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Secret Name: $SECRET_NAME"
echo "Namespace: $NAMESPACE"
echo "SSH Key: $SSH_KEY_PATH"
echo ""

# 기존 Secret 확인
if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "⚠️  Secret already exists. Updating..."
    kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE"
fi

# Secret 생성
kubectl create secret generic "$SECRET_NAME" \
    --from-file=ssh-privatekey="$SSH_KEY_PATH" \
    --namespace="$NAMESPACE"

# Secret 확인
echo ""
echo "✅ Secret created successfully!"
echo ""
echo "📋 Secret Details:"
kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o yaml | grep -A 2 "ssh-privatekey:" || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SSH Key Secret 생성 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 다음 단계:"
echo "   1. ArgoCD Application에 Hooks가 포함되어 있는지 확인"
echo "   2. ArgoCD Application Sync 실행"
echo "   3. PreSync Hook에서 이 Secret을 사용하여 Ansible 실행"
echo ""
echo "🔍 확인 명령어:"
echo "   kubectl get secret $SECRET_NAME -n $NAMESPACE"
echo "   kubectl describe secret $SECRET_NAME -n $NAMESPACE"

