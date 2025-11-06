#!/bin/bash
# Kubernetes 클러스터 구축 스크립트
# Terraform apply → Ansible 실행
# (삭제는 cleanup.sh에서 처리)

set -e  # 에러 발생 시 즉시 중단

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
ANSIBLE_DIR="$PROJECT_ROOT/ansible"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Kubernetes 클러스터 구축"
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
  read -p "⚠️  새로운 인프라를 구축하시겠습니까? (yes/no): " CONFIRM
  if [ "$CONFIRM" != "yes" ]; then
    echo "❌ 취소되었습니다."
    exit 0
  fi
else
  echo "🤖 자동 모드로 실행 중..."
fi

cd "$TERRAFORM_DIR"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Terraform Apply - 새 인프라 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔧 Terraform 초기화..."
terraform init -migrate-state -upgrade
echo ""

# 기존 리소스 확인
if terraform state list >/dev/null 2>&1; then
  RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
  echo "📊 현재 Terraform 리소스 개수: $RESOURCE_COUNT"
  
  if [ "$RESOURCE_COUNT" -gt 0 ]; then
    echo ""
    echo "⚠️  기존 인프라가 존재합니다!"
    echo ""
    echo "💡 인프라를 먼저 삭제하려면:"
    echo "   ./scripts/cleanup.sh"
    echo ""
    
    if [ "$AUTO_MODE" != "true" ]; then
      read -p "기존 인프라를 유지하고 계속하시겠습니까? (yes/no): " CONTINUE
      if [ "$CONTINUE" != "yes" ]; then
        echo "❌ 취소되었습니다."
        exit 0
      fi
    else
      echo "🤖 자동 모드: 기존 인프라를 유지하고 계속합니다..."
    fi
    echo ""
  fi
fi

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
  "Worker 2: " + .worker_2_public_ip.value,
  "Storage: " + .storage_public_ip.value
' 2>/dev/null || echo "  (인스턴스 정보 확인 중...)"
echo ""

# SSM Agent 등록 대기
echo "⏳ SSM Agent 등록 및 초기화 대기 (60초)..."
sleep 60
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Ansible Inventory 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform 디렉토리로 이동 확인
cd "$TERRAFORM_DIR"
echo "📍 현재 디렉토리: $(pwd)"

# Terraform backend 재확인 (output 실행 전)
echo "🔧 Terraform backend 확인..."
terraform init -migrate-state -upgrade -input=false
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
echo "3️⃣ SSH 연결 테스트"
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
echo "4️⃣ Ansible Playbook 실행 (Kubernetes 설치)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform output 추출 (ALB Controller용)
cd "$TERRAFORM_DIR"
echo "📊 Terraform output 추출 중..."

# State 파일 새로고침 (최신 상태 반영)
echo "🔧 Terraform state 새로고침 중..."
terraform refresh -input=false >/dev/null 2>&1 || true

# Output 확인 및 추출
if ! terraform output vpc_id >/dev/null 2>&1; then
    echo "⚠️  vpc_id output을 찾을 수 없습니다."
    echo "   Terraform apply가 완료되었는지 확인하세요."
    echo ""
    echo "수동 확인 명령어:"
    echo "  cd $TERRAFORM_DIR"
    echo "  terraform output"
    exit 1
fi

VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
if [ -z "$VPC_ID" ]; then
    echo "❌ vpc_id를 가져올 수 없습니다!"
    exit 1
fi

ACM_ARN=$(terraform output -raw acm_certificate_arn 2>/dev/null || echo "")
echo "  VPC ID: $VPC_ID"
echo "  ACM ARN: ${ACM_ARN:-'(없음)'}"
echo ""

cd "$ANSIBLE_DIR"

# Extra vars로 전달
ansible-playbook -i inventory/hosts.ini site.yml \
  -e "vpc_id=$VPC_ID" \
  -e "acm_certificate_arn=$ACM_ARN"

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
echo "✅ 클러스터 구축 완료!"
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

