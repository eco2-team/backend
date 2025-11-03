#!/bin/bash
# K8s 클러스터 삭제 스크립트

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "⚠️  경고: 모든 인프라가 삭제됩니다!"
echo "================================================"

cd "$TERRAFORM_DIR"
echo "📍 현재 디렉토리: $(pwd)"
echo ""

# 현재 리소스 확인
echo "현재 생성된 리소스:"
terraform show | grep "resource\|instance_type\|vpc_id" || echo "리소스 없음"

echo ""
read -p "정말로 삭제하시겠습니까? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ 취소되었습니다."
    exit 1
fi

echo ""
echo "🗑️  인프라 삭제 중..."
terraform destroy -auto-approve

echo ""
echo "✅ 모든 리소스가 삭제되었습니다."
echo ""
echo "비용 절감:"
echo "- EC2 인스턴스: $105/월 → $0"
echo "- 다시 생성: ./scripts/provision.sh 실행"

