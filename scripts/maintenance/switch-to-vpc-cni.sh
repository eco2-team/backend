#!/bin/bash
# AWS VPC CNI 전환 스크립트
# Calico → AWS VPC CNI 전환

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

MASTER_IP="${MASTER_IP:-52.79.238.50}"
SSH_KEY="${SSH_KEY:-~/.ssh/sesacthon}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 AWS VPC CNI 전환 스크립트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "이 스크립트는 다음을 수행합니다:"
echo "  1. 현재 클러스터 백업"
echo "  2. 클러스터 완전 삭제 (cleanup.sh)"
echo "  3. VPC CNI로 재구축 (build-cluster.sh)"
echo "  4. ALB Ingress target-type을 ip로 복원"
echo ""
echo "⚠️  주의: 클러스터 재구축으로 15-20분 소요됩니다"
echo ""

read -p "계속하시겠습니까? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "취소되었습니다."
    exit 0
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: 현재 설정 백업"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

mkdir -p backup/pre-vpc-cni

echo "클러스터 정보 백업 중..."
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get nodes -o wide" > backup/pre-vpc-cni/nodes.txt || true
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get pods -A -o wide" > backup/pre-vpc-cni/pods.txt || true
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get svc -A" > backup/pre-vpc-cni/services.txt || true
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get ingress -A" > backup/pre-vpc-cni/ingress.txt || true

echo "✅ 백업 완료: backup/pre-vpc-cni/"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: 클러스터 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$(dirname "$0")"
./cleanup.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: VPC CNI로 클러스터 재구축"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# CNI 플러그인 설정을 vpc-cni로 변경
echo "CNI 플러그인을 vpc-cni로 설정..."
sed -i.bak 's/cni_plugin: "calico"/cni_plugin: "vpc-cni"/' ../ansible/inventory/group_vars/all.yml || \
    echo 'cni_plugin: "vpc-cni"' >> ../ansible/inventory/group_vars/all.yml

./build-cluster.sh

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Pod IP 범위 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "VPC CIDR 확인..."
cd "$TERRAFORM_DIR"
VPC_CIDR=$(terraform output -raw vpc_cidr 2>/dev/null || echo "10.0.0.0/16")
echo "  VPC CIDR: $VPC_CIDR"
echo ""

echo "현재 Pod IP 샘플:"
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get pods -A -o wide | grep -v NAMESPACE | head -10 | awk '{print \$1 \"\\t\" \$2 \"\\t\" \$7}'"
echo ""

echo "✅ Pod IP가 VPC CIDR 내에 할당되었는지 확인하세요"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: ALB 상태 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Ingress 리소스 확인 (ALB 생성까지 3-5분 소요)..."
ssh -i "$SSH_KEY" ubuntu@"$MASTER_IP" "kubectl get ingress -A"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ AWS VPC CNI 전환 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "다음 단계:"
echo "  1. 5분 후 ALB 주소 확인:"
echo "     ssh -i $SSH_KEY ubuntu@$MASTER_IP \"kubectl get ingress -A\""
echo ""
echo "  2. ALB Target Health 확인:"
echo "     AWS Console → EC2 → Target Groups → 'k8s-...' 선택"
echo "     → Targets 탭 → Status가 'healthy' 확인"
echo ""
echo "  3. 브라우저 테스트:"
echo "     https://growbin.app/"
echo ""

