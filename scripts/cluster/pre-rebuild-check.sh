#!/bin/bash
# Rebuild 전 체크리스트 및 준비 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Rebuild 전 체크리스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 색상 코드
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 체크 함수
check_pass() {
  echo -e "${GREEN}✅ $1${NC}"
}

check_warn() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

check_fail() {
  echo -e "${RED}❌ $1${NC}"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. AWS 자격 증명 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【1】 AWS 자격 증명 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
  check_pass "AWS 자격 증명 환경변수 설정됨"
elif [ -f ~/.aws/credentials ]; then
  check_pass "AWS 자격 증명 파일 존재 (~/.aws/credentials)"
else
  check_fail "AWS 자격 증명이 없습니다!"
  echo "   export AWS_ACCESS_KEY_ID=..."
  echo "   export AWS_SECRET_ACCESS_KEY=..."
  exit 1
fi

# 리전 확인
if aws configure get region >/dev/null 2>&1; then
  REGION=$(aws configure get region)
  if [ "$REGION" = "ap-northeast-2" ]; then
    check_pass "AWS 리전: ap-northeast-2 (Seoul) ✅"
  else
    check_warn "AWS 리전: $REGION (예상: ap-northeast-2)"
  fi
else
  check_warn "AWS 리전이 설정되지 않음 (기본값 사용)"
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. SSH 키 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【2】 SSH 키 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -f ~/.ssh/sesacthon.pem ]; then
  check_pass "SSH 키 파일 존재 (~/.ssh/sesacthon.pem)"
  
  # 권한 확인
  PERMS=$(stat -f "%OLp" ~/.ssh/sesacthon.pem 2>/dev/null || stat -c "%a" ~/.ssh/sesacthon.pem 2>/dev/null)
  if [ "$PERMS" = "400" ] || [ "$PERMS" = "600" ]; then
    check_pass "SSH 키 권한 올바름 ($PERMS)"
  else
    check_warn "SSH 키 권한이 올바르지 않음 ($PERMS)"
    echo "   chmod 400 ~/.ssh/sesacthon.pem"
  fi
else
  check_fail "SSH 키가 없습니다! (~/.ssh/sesacthon.pem)"
  echo "   AWS Console → EC2 → Key Pairs에서 다운로드"
  exit 1
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Terraform 설정 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【3】 Terraform 설정 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 현재 디렉토리 저장
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$WORKSPACE_DIR/terraform"

# Terraform 디렉토리 확인
if [ ! -d "$TERRAFORM_DIR" ]; then
  check_fail "Terraform 디렉토리를 찾을 수 없습니다: $TERRAFORM_DIR"
  exit 1
fi

# 리전 확인
if grep -q 'aws_region = "ap-northeast-2"' "$TERRAFORM_DIR/terraform.tfvars" 2>/dev/null; then
  check_pass "Terraform 리전: ap-northeast-2 ✅"
else
  check_fail "terraform.tfvars의 aws_region이 ap-northeast-2가 아닙니다!"
  exit 1
fi

# 노드 모듈 확인
MODULES=("master" "worker_1" "worker_2" "rabbitmq" "postgresql" "redis" "monitoring")
for MODULE in "${MODULES[@]}"; do
  if grep -q "module \"$MODULE\"" "$TERRAFORM_DIR/main.tf" 2>/dev/null; then
    check_pass "Terraform 모듈: $MODULE ✅"
  else
    check_fail "Terraform 모듈 누락: $MODULE"
    exit 1
  fi
done

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Ansible 설정 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【4】 Ansible 설정 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ANSIBLE_DIR="$WORKSPACE_DIR/ansible"

# CNI 설정 확인
if grep -q 'cni_plugin: "calico"' "$ANSIBLE_DIR/inventory/group_vars/all.yml" 2>/dev/null; then
  check_pass "CNI 플러그인: Calico ✅"
else
  check_warn "CNI 플러그인이 Calico가 아닙니다!"
fi

# Pod CIDR 확인
if grep -q 'pod_network_cidr: "192.168.0.0/16"' "$ANSIBLE_DIR/inventory/group_vars/all.yml" 2>/dev/null; then
  check_pass "Pod CIDR: 192.168.0.0/16 ✅"
else
  check_fail "pod_network_cidr이 192.168.0.0/16이 아닙니다!"
  exit 1
fi

# CNI 플레이북 노드 수 확인
if grep -q 'EXPECTED_WORKERS=6' "$ANSIBLE_DIR/playbooks/04-cni-install.yml" 2>/dev/null; then
  check_pass "CNI 플레이북 Worker 수: 6 ✅"
else
  check_fail "ansible/playbooks/04-cni-install.yml의 EXPECTED_WORKERS가 6이 아닙니다!"
  exit 1
fi

if grep -q 'EXPECTED_TOTAL_NODES=7' "$ANSIBLE_DIR/playbooks/04-cni-install.yml" 2>/dev/null; then
  check_pass "CNI 플레이북 Total 노드 수: 7 ✅"
else
  check_fail "ansible/playbooks/04-cni-install.yml의 EXPECTED_TOTAL_NODES가 7이 아닙니다!"
  exit 1
fi

# 노드 레이블 확인
NODE_LABELS=("k8s-worker-1" "k8s-worker-2" "k8s-rabbitmq" "k8s-postgresql" "k8s-redis" "k8s-monitoring")
for NODE in "${NODE_LABELS[@]}"; do
  if grep -q "kubectl label nodes $NODE" "$ANSIBLE_DIR/site.yml" 2>/dev/null; then
    check_pass "노드 레이블 설정: $NODE ✅"
  else
    check_warn "노드 레이블 누락 가능: $NODE"
  fi
done

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 환경변수 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【5】 환경변수 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# RabbitMQ 비밀번호
ENV_WARNINGS=0

if [ -n "$RABBITMQ_PASSWORD" ]; then
  check_pass "RABBITMQ_PASSWORD 설정됨 ✅"
else
  check_warn "RABBITMQ_PASSWORD 미설정 (Ansible 기본값 사용 예정)"
  ENV_WARNINGS=$((ENV_WARNINGS + 1))
fi

# Grafana 비밀번호
if [ -n "$GRAFANA_PASSWORD" ]; then
  check_pass "GRAFANA_PASSWORD 설정됨 ✅"
else
  check_warn "GRAFANA_PASSWORD 미설정 (Ansible 기본값 사용 예정)"
  ENV_WARNINGS=$((ENV_WARNINGS + 1))
fi

# PostgreSQL 비밀번호
if [ -n "$POSTGRES_PASSWORD" ]; then
  check_pass "POSTGRES_PASSWORD 설정됨 ✅"
else
  check_warn "POSTGRES_PASSWORD 미설정 (Ansible 기본값 사용 예정)"
  ENV_WARNINGS=$((ENV_WARNINGS + 1))
fi

if [ $ENV_WARNINGS -gt 0 ]; then
  echo ""
  echo "💡 환경변수 설정 방법:"
  echo ""
  echo "   1️⃣ 임시 설정 (현재 세션만):"
  echo "      export RABBITMQ_PASSWORD='your-secure-password'"
  echo "      export GRAFANA_PASSWORD='your-secure-password'"
  echo "      export POSTGRES_PASSWORD='your-secure-password'"
  echo ""
  echo "   2️⃣ 영구 설정 (~/.zshrc 또는 ~/.bashrc):"
  echo "      echo 'export RABBITMQ_PASSWORD=\"your-secure-password\"' >> ~/.zshrc"
  echo "      echo 'export GRAFANA_PASSWORD=\"your-secure-password\"' >> ~/.zshrc"
  echo "      echo 'export POSTGRES_PASSWORD=\"your-secure-password\"' >> ~/.zshrc"
  echo "      source ~/.zshrc"
  echo ""
  echo "   3️⃣ .env 파일 사용 (권장):"
  echo "      cat > \$WORKSPACE_DIR/.env << EOF"
  echo "export RABBITMQ_PASSWORD='your-secure-password'"
  echo "export GRAFANA_PASSWORD='your-secure-password'"
  echo "export POSTGRES_PASSWORD='your-secure-password'"
  echo "EOF"
  echo "      source .env"
  echo ""
  echo "   ⚠️  미설정 시 Ansible 기본값 사용:"
  echo "      - RABBITMQ_PASSWORD: changeme (ansible/inventory/group_vars/all.yml)"
  echo "      - GRAFANA_PASSWORD: admin123 (ansible/inventory/group_vars/all.yml)"
  echo "      - POSTGRES_PASSWORD: changeme (ansible/inventory/group_vars/all.yml)"
  echo ""
  echo "   ℹ️  GitHub Actions CI/CD는 별도 Secrets 사용 (GITHUB_SECRETS_GUIDE.md 참조)"
  echo ""
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 기존 리소스 확인 (충돌 방지)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【6】 기존 AWS 리소스 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# VPC 확인
VPC_COUNT=$(aws ec2 describe-vpcs --filters "Name=tag:Project,Values=sesacthon" --query 'Vpcs | length(@)' --output text 2>/dev/null || echo "0")
if [ "$VPC_COUNT" -gt 0 ]; then
  check_warn "기존 VPC 존재 ($VPC_COUNT개)"
  echo "   ⚠️  cleanup.sh를 먼저 실행하세요!"
else
  check_pass "기존 VPC 없음 (새로 생성 가능)"
fi

# EC2 인스턴스 확인
EC2_COUNT=$(aws ec2 describe-instances --filters "Name=tag:Project,Values=sesacthon" "Name=instance-state-name,Values=running,pending,stopped" --query 'Reservations[*].Instances | length(@[])' --output text 2>/dev/null || echo "0")
if [ "$EC2_COUNT" -gt 0 ]; then
  check_warn "기존 EC2 인스턴스 존재 ($EC2_COUNT개)"
  echo "   ⚠️  cleanup.sh를 먼저 실행하세요!"
else
  check_pass "기존 EC2 인스턴스 없음 (새로 생성 가능)"
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 최종 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【최종 요약】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📊 예상 클러스터 구성:"
echo ""
echo "  총 7개 노드:"
echo "  ├─ Master (t3.large, 8GB)     - Control Plane"
echo "  ├─ Worker-1 (t3.medium, 4GB)  - Application Pods"
echo "  ├─ Worker-2 (t3.medium, 4GB)  - Celery Workers"
echo "  ├─ RabbitMQ (t3.small, 2GB)   - Message Queue only"
echo "  ├─ PostgreSQL (t3.small, 2GB) - Database only"
echo "  ├─ Redis (t3.small, 2GB)      - Cache only"
echo "  └─ Monitoring (t3.medium, 4GB) - Prometheus + Grafana"
echo ""
echo "  총 vCPU: 11"
echo "  총 Memory: 22GB"
echo "  총 비용: ~\$214/month"
echo ""

echo "🌐 네트워크 설정:"
echo ""
echo "  리전: ap-northeast-2 (Seoul)"
echo "  VPC CIDR: 10.0.0.0/16"
echo "  Pod CIDR: 192.168.0.0/16 (Calico VXLAN)"
echo "  Service CIDR: 10.96.0.0/12"
echo ""
echo "  CNI: Calico (VXLAN Always, BGP Disabled)"
echo "  Ingress: ALB (target-type: instance)"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$VPC_COUNT" -gt 0 ] || [ "$EC2_COUNT" -gt 0 ]; then
  echo -e "${YELLOW}⚠️  기존 리소스가 존재합니다!${NC}"
  echo ""
  echo "다음 명령어로 기존 리소스를 먼저 정리하세요:"
  echo ""
  echo "  ./scripts/cluster/cleanup.sh"
  echo ""
  echo "또는 강제로 진행하려면 (권장하지 않음):"
  echo "  ./scripts/cluster/build-cluster.sh --force"
  echo ""
  exit 1
else
  echo -e "${GREEN}✅ Rebuild 준비 완료!${NC}"
  echo ""
  echo "다음 명령어로 클러스터를 구축하세요:"
  echo ""
  echo "  ./scripts/cluster/build-cluster.sh"
  echo ""
  echo "예상 소요 시간: ~20-30분"
  echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

