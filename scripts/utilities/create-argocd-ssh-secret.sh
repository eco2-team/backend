#!/bin/bash
# ArgoCD용 SSH Key Secret 생성 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 ArgoCD용 SSH Key Secret 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# SSH Key 경로
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"

# SSH Key 존재 확인
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH Key를 찾을 수 없습니다: $SSH_KEY"
    echo ""
    echo "SSH Key를 생성하거나 경로를 지정하세요:"
    echo "  SSH_KEY=/path/to/key $0"
    exit 1
fi

echo "✓ SSH Key: $SSH_KEY"

# ArgoCD Namespace 확인
if ! kubectl get namespace argocd &> /dev/null; then
    echo "❌ argocd namespace가 없습니다"
    echo "먼저 ArgoCD를 설치하세요"
    exit 1
fi

echo "✓ ArgoCD namespace 존재"

# 기존 Secret 삭제 (있다면)
if kubectl get secret k8s-cluster-ssh-key -n argocd &> /dev/null; then
    echo ""
    echo "기존 Secret 삭제 중..."
    kubectl delete secret k8s-cluster-ssh-key -n argocd
fi

# Secret 생성
echo ""
echo "Secret 생성 중..."
kubectl create secret generic k8s-cluster-ssh-key \
    --from-file=ssh-privatekey="$SSH_KEY" \
    --namespace=argocd

# Secret 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Secret 생성 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
kubectl get secret k8s-cluster-ssh-key -n argocd
echo ""
echo "📝 다음 단계:"
echo "  1. ArgoCD Application 등록"
echo "  2. Hooks 테스트"

