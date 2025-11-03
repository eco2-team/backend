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
echo "ℹ️  Kubernetes 리소스 정리는 destroy-with-cleanup.sh에서 처리합니다."
echo "   이 스크립트는 Terraform 인프라만 삭제합니다."
echo ""

cd "$TERRAFORM_DIR"

echo "🔧 Terraform 초기화..."
terraform init -migrate-state -upgrade
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 현재 인프라 리소스 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform state 파일 존재 확인
if ! terraform state list >/dev/null 2>&1; then
  echo "ℹ️  State 파일 없음 (새 배포)"
  echo "   기존 인프라가 없습니다. 바로 생성 단계로 진행합니다."
  echo ""
else
  # 리소스 개수 확인
  RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
  echo "📊 현재 리소스 개수: $RESOURCE_COUNT"
  echo ""
  
  if [ "$RESOURCE_COUNT" -gt 0 ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 삭제될 주요 리소스 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # EC2 인스턴스 확인
    echo "💻 EC2 인스턴스:"
    terraform state list 2>/dev/null | grep -E "module\.(master|worker_1|worker_2|storage)\.aws_instance" || echo "  (없음)"
    echo ""
    
    # Elastic IP 확인
    echo "🌐 Elastic IP:"
    terraform state list 2>/dev/null | grep -E "aws_eip\." || echo "  (없음)"
    echo ""
    
    # S3 버킷 확인
    echo "🪣 S3 버킷:"
    terraform state list 2>/dev/null | grep -E "aws_s3_bucket|module\..*s3" || echo "  (없음)"
    echo ""
    
    # VPC 리소스 확인
    echo "🔒 VPC 리소스 (Security Groups, Subnets, etc.):"
    VPC_RESOURCES=$(terraform state list 2>/dev/null | grep -E "module\.(vpc|security_groups)" | wc -l | tr -d ' ')
    echo "  VPC 관련 리소스: $VPC_RESOURCES개"
    echo ""
    
    # 전체 리소스 요약
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 전체 리소스 목록 (일부):"
    terraform state list 2>/dev/null | head -20
    if [ "$RESOURCE_COUNT" -gt 20 ]; then
      echo "  ... 및 $((RESOURCE_COUNT - 20))개 추가 리소스"
    fi
    echo ""
    
    # 삭제 확인
    if [ "$AUTO_MODE" != "true" ]; then
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      read -p "⚠️  위 리소스들을 삭제하시겠습니까? (yes/no): " CONFIRM_DELETE
      if [ "$CONFIRM_DELETE" != "yes" ]; then
        echo "❌ 삭제가 취소되었습니다."
        exit 0
      fi
    else
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      echo "🤖 자동 모드: 5초 후 삭제 시작..."
      echo "   Ctrl+C를 눌러 취소할 수 있습니다."
      sleep 5
    fi
    echo ""
  else
    echo "ℹ️  리소스가 없습니다. 바로 생성 단계로 진행합니다."
    echo ""
  fi
fi

echo "🗑️  Terraform destroy 실행..."
terraform destroy -auto-approve

if [ $? -ne 0 ]; then
  echo ""
  echo "❌ Terraform destroy 실패!"
  echo ""
  echo "💡 VPC 삭제 장시간 대기 문제인 경우:"
  echo "   ./scripts/destroy-with-cleanup.sh를 먼저 실행하여 리소스를 정리하세요."
  echo ""
  VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
  AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-northeast-2")
  if [ -n "$VPC_ID" ]; then
    echo "남은 리소스 확인:"
    echo "  aws ec2 describe-volumes --region $AWS_REGION"
    echo "  aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID --region $AWS_REGION"
  fi
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

echo "🔧 Terraform 초기화 (재확인)..."
terraform init -migrate-state -upgrade
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

# Terraform output 추출 (ALB Controller용)
cd "$TERRAFORM_DIR"
echo "📊 Terraform output 추출 중..."
VPC_ID=$(terraform output -raw vpc_id)
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

