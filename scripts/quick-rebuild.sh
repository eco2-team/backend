#!/bin/bash
# 빠른 재구축 (확인 없이 자동 실행)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🚀 빠른 재구축 시작..."
echo ""

cd "$PROJECT_ROOT/terraform"
terraform destroy -auto-approve
sleep 30
terraform apply -auto-approve
sleep 60
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini

cd "$PROJECT_ROOT/ansible"
ansible-playbook -i inventory/hosts.ini site.yml

echo ""
echo "✅ 완료!"


