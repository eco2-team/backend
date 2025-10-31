#!/bin/bash
# Kubernetes 클러스터 완전 재구축 스크립트
# Terraform destroy → apply → Ansible 실행

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
ANSIBLE_DIR="$PROJECT_ROOT/ansible"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Kubernetes 클러스터 완전 재구축"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "작업 디렉토리:"
echo "  - Terraform: $TERRAFORM_DIR"
echo "  - Ansible: $ANSIBLE_DIR"
echo ""

# 자동 실행 모드 확인
AUTO_MODE=${AUTO_MODE:-false}

if [ "$AUTO_MODE" != "true" ]; then
  # 확인 프롬프트
  read -p "⚠️  기존 인프라를 삭제하고 재구축하시겠습니까? (yes/no): " CONFIRM
  if [ "$CONFIRM" != "yes" ]; then
    echo "❌ 취소되었습니다."
    exit 0
  fi
else
  echo "🤖 자동 모드로 실행 중..."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Terraform Destroy - 기존 인프라 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$TERRAFORM_DIR"

echo "🔍 현재 인프라 상태 확인..."
terraform show || true
echo ""

echo "🗑️  Terraform destroy 실행..."
terraform destroy -auto-approve

if [ $? -ne 0 ]; then
  echo "❌ Terraform destroy 실패!"
  exit 1
fi

echo "✅ 기존 인프라 삭제 완료"
echo ""

# 대기 시간 (AWS 리소스 완전 삭제)
echo "⏳ AWS 리소스 완전 삭제 대기 (30초)..."
sleep 30
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Terraform Apply - 새 인프라 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🚀 Terraform apply 실행..."
terraform apply -auto-approve

if [ $? -ne 0 ]; then
  echo "❌ Terraform apply 실패!"
  exit 1
fi

echo "✅ 새 인프라 생성 완료"
echo ""

# 인스턴스 정보 출력
echo "📋 생성된 인스턴스 정보:"
terraform output -json | jq -r '
  "Master: " + .master_public_ip.value,
  "Worker 1: " + .worker_1_public_ip.value,
  "Worker 2: " + .worker_2_public_ip.value
'
echo ""

# SSM Agent 등록 대기
echo "⏳ SSM Agent 등록 및 초기화 대기 (60초)..."
sleep 60
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Ansible Inventory 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📝 Ansible inventory 생성 중..."
terraform output -raw ansible_inventory > "$ANSIBLE_DIR/inventory/hosts.ini"

if [ $? -ne 0 ]; then
  echo "❌ Inventory 생성 실패!"
  exit 1
fi

echo "✅ Inventory 생성 완료"
echo ""
echo "생성된 Inventory:"
cat "$ANSIBLE_DIR/inventory/hosts.ini"
echo ""

# SSH 연결 테스트
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ SSH 연결 테스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$ANSIBLE_DIR"

echo "🔍 Ansible ping 테스트..."
ansible all -i inventory/hosts.ini -m ping || true
echo ""

# Ansible 실행 확인
if [ "$AUTO_MODE" != "true" ]; then
  read -p "✅ Ansible playbook을 실행하시겠습니까? (yes/no): " RUN_ANSIBLE
  if [ "$RUN_ANSIBLE" != "yes" ]; then
    echo "⚠️  Ansible playbook을 건너뜁니다."
    echo ""
    echo "수동 실행 명령어:"
    echo "  cd $ANSIBLE_DIR"
    echo "  ansible-playbook -i inventory/hosts.ini site.yml"
    exit 0
  fi
else
  echo "🤖 자동으로 Ansible playbook 실행..."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ Ansible Playbook 실행 (Kubernetes 설치)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ansible-playbook -i inventory/hosts.ini site.yml

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Ansible playbook 실패!"
  echo ""
  echo "디버깅 명령어:"
  echo "  ./scripts/connect-ssh.sh master"
  echo "  kubectl get nodes"
  echo "  kubectl get pods -A"
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 클러스터 재구축 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 다음 단계:"
echo "  1. 클러스터 접속:"
echo "     ./scripts/connect-ssh.sh master"
echo ""
echo "  2. 노드 확인:"
echo "     kubectl get nodes -o wide"
echo ""
echo "  3. Pod 확인:"
echo "     kubectl get pods -A"
echo ""
echo "  4. 도메인 확인:"
echo "     https://growbin.app"
echo "     https://api.growbin.app"
echo ""

