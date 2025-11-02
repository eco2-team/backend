#!/bin/bash
# 빠른 재구축 (확인 없이 자동 실행)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 빠른 재구축 시작..."
echo ""

cd "$PROJECT_ROOT/terraform"
echo "📍 현재 디렉토리: $(pwd)"
echo ""

echo "🔧 Terraform 초기화..."
terraform init -migrate-state -upgrade -input=false

echo "🗑️  기존 인프라 삭제..."
terraform destroy -auto-approve
sleep 30

echo "🔧 Terraform 재초기화..."
terraform init -migrate-state -upgrade -input=false

echo "🚀 새 인프라 생성..."
terraform apply -auto-approve
sleep 60

echo "📝 Inventory 생성..."
terraform init -migrate-state -upgrade -input=false
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

echo "📊 Terraform output 추출..."
VPC_ID=$(terraform output -raw vpc_id)
ACM_ARN=$(terraform output -raw acm_certificate_arn 2>/dev/null || echo "")

cd "$PROJECT_ROOT/ansible"
ansible-playbook -i inventory/hosts.ini site.yml \
  -e "vpc_id=$VPC_ID" \
  -e "acm_certificate_arn=$ACM_ARN"

echo ""
echo "✅ 완료!"


