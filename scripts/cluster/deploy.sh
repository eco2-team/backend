#!/bin/bash
# 14-Node 클러스터 완전 자동 배포 스크립트 v2.0
# Terraform + Ansible 기반 (GitOps Ready)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
ANSIBLE_DIR="$PROJECT_ROOT/ansible"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).log"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 로그 함수
log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ❌ ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠️  WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${CYAN}[$(date +'%H:%M:%S')] ℹ️  INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# 헤더 출력
print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# 시작 시간 기록
START_TIME=$(date +%s)

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

print_header "🚀 14-Node 클러스터 완전 자동 배포"

log "배포 시작: $(date)"
log "로그 파일: $LOG_FILE"
log ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣ 사전 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "1️⃣ 사전 확인"

# AWS 인증 확인
log "AWS 인증 확인 중..."
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS 인증 실패"
    log_info "aws configure를 실행하여 AWS 인증 정보를 설정하세요"
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query 'Account' --output text)
AWS_USER=$(aws sts get-caller-identity --query 'Arn' --output text | awk -F'/' '{print $NF}')
log "✅ AWS 계정: $AWS_ACCOUNT (사용자: $AWS_USER)"

# AWS Region 확인
AWS_REGION=$(aws configure get region || echo "ap-northeast-2")
log "✅ AWS Region: $AWS_REGION"

# vCPU 할당량 확인
log "vCPU 할당량 확인 중..."
VCPU_LIMIT=$(aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region "$AWS_REGION" \
    --query 'Quota.Value' \
    --output text 2>/dev/null || echo "0")

log_info "현재 vCPU 할당량: $VCPU_LIMIT"

if (( $(echo "$VCPU_LIMIT < 32" | bc -l) )); then
    log_warn "vCPU 할당량이 부족합니다 (필요: 32, 현재: $VCPU_LIMIT)"
    log_info "계속 진행하시겠습니까? (yes/no)"
    read -r response
    if [ "$response" != "yes" ]; then
        log "배포 취소됨"
        exit 0
    fi
fi

# SSH 키 확인
log "SSH 키 확인 중..."
if [ ! -f ~/.ssh/sesacthon.pem ]; then
    log_error "SSH 키가 없습니다: ~/.ssh/sesacthon.pem"
    exit 1
fi
log "✅ SSH 키 확인 완료"

# 필수 도구 확인
log "필수 도구 확인 중..."
for tool in terraform ansible jq; do
    if ! command -v $tool &> /dev/null; then
        log_error "$tool이 설치되어 있지 않습니다"
        exit 1
    fi
    VERSION=$($tool --version 2>&1 | head -1)
    log "✅ $tool: $VERSION"
done

# kubectl 확인 (선택적 - 로컬 클러스터 관리용)
if ! command -v kubectl &> /dev/null; then
    log_warn "kubectl이 설치되어 있지 않습니다 (로컬에서 클러스터 관리 시 필요)"
    log_info "설치 방법: brew install kubectl"
else
    VERSION=$(kubectl version --client 2>&1 | head -1)
    log "✅ kubectl: $VERSION"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2️⃣ Terraform 인프라 프로비저닝
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "2️⃣ Terraform 인프라 프로비저닝 (15-20분)"

cd "$TERRAFORM_DIR"

# Terraform 초기화
log "Terraform 초기화 중..."
if terraform init -upgrade 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Terraform 초기화 완료"
else
    log_error "Terraform 초기화 실패"
    exit 1
fi

# Terraform Plan
log "Terraform plan 실행 중..."
if terraform plan -out=tfplan 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Terraform plan 완료"
else
    log_error "Terraform plan 실패"
    exit 1
fi

# Terraform Apply
log "Terraform apply 실행 중... (예상 시간: 15-20분)"
log_warn "CloudFront 생성 시 10-15분 소요됩니다"

if terraform apply tfplan 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Terraform apply 완료"
else
    log_error "Terraform apply 실패"
    exit 1
fi

# 리소스 확인
log "생성된 리소스 확인 중..."
INSTANCE_COUNT=$(terraform state list | grep -c "aws_instance.this" || echo "0")
log_info "생성된 EC2 인스턴스: $INSTANCE_COUNT개"

if [ "$INSTANCE_COUNT" -ne 14 ]; then
    log_warn "예상과 다른 인스턴스 수입니다 (예상: 14개, 실제: $INSTANCE_COUNT개)"
fi

# VPC ID 확인
VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
if [ -n "$VPC_ID" ]; then
    log "✅ VPC ID: $VPC_ID"
else
    log_error "VPC ID를 가져올 수 없습니다"
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3️⃣ Ansible Inventory 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "3️⃣ Ansible Inventory 생성"

log "Ansible Inventory 생성 중..."
if terraform output -raw ansible_inventory > "$ANSIBLE_DIR/inventory/hosts.ini" 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Inventory 생성 완료: $ANSIBLE_DIR/inventory/hosts.ini"
else
    log_error "Inventory 생성 실패"
    exit 1
fi

# Inventory 검증
log "Inventory 검증 중..."
MASTER_IP=$(grep "k8s-master" "$ANSIBLE_DIR/inventory/hosts.ini" | awk '{print $2}' | cut -d'=' -f2)
if [ -n "$MASTER_IP" ]; then
    log "✅ Master 노드 IP: $MASTER_IP"
else
    log_error "Master 노드 IP를 찾을 수 없습니다"
    exit 1
fi

# SSH 연결 대기 (EC2 인스턴스 부팅 시간)
log "EC2 인스턴스 부팅 대기 중... (60초)"
sleep 60

# SSH 연결 테스트
log "SSH 연결 테스트 중..."
cd "$ANSIBLE_DIR"

MAX_RETRY=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRY ]; do
    log_info "SSH 연결 시도 $((RETRY_COUNT + 1))/$MAX_RETRY..."
    
    if ansible all -m ping -i inventory/hosts.ini 2>&1 | tee -a "$LOG_FILE" | grep -q "SUCCESS"; then
        log "✅ 모든 노드 SSH 연결 성공"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -lt $MAX_RETRY ]; then
            log_warn "SSH 연결 실패, 30초 후 재시도..."
            sleep 30
        else
            log_error "SSH 연결 실패 (최대 재시도 횟수 초과)"
            exit 1
        fi
    fi
done

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4️⃣ Ansible Playbook 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "4️⃣ Ansible Playbook 실행 (15-20분)"

cd "$ANSIBLE_DIR"

# Terraform Output 가져오기 (ALB Controller 설치용)
log "Terraform Output 조회 중..."
cd "$TERRAFORM_DIR"
VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
ACM_CERT_ARN=$(terraform output -raw acm_certificate_arn 2>/dev/null || echo "")
cd "$ANSIBLE_DIR"

if [ -z "$VPC_ID" ]; then
    log_warn "VPC ID를 찾을 수 없습니다. ALB Controller 설치가 실패할 수 있습니다"
else
    log "✅ VPC ID: $VPC_ID"
fi

# site.yml 실행 (Bootstrap)
log "site.yml 실행 중... (예상 시간: 12-15분)"
log_info "Docker, Kubernetes 설치 및 클러스터 구성"

# Terraform output을 extra-vars로 전달
EXTRA_VARS=""
if [ -n "$VPC_ID" ]; then
    EXTRA_VARS="vpc_id=$VPC_ID"
fi
if [ -n "$ACM_CERT_ARN" ]; then
    if [ -n "$EXTRA_VARS" ]; then
        EXTRA_VARS="$EXTRA_VARS acm_certificate_arn=$ACM_CERT_ARN"
    else
        EXTRA_VARS="acm_certificate_arn=$ACM_CERT_ARN"
    fi
fi

if [ -n "$EXTRA_VARS" ]; then
    log_info "Extra vars: $EXTRA_VARS"
    if ansible-playbook site.yml -i inventory/hosts.ini -e "$EXTRA_VARS" 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ site.yml 실행 완료"
    else
        log_error "site.yml 실행 실패"
        exit 1
    fi
else
    if ansible-playbook site.yml -i inventory/hosts.ini 2>&1 | tee -a "$LOG_FILE"; then
        log "✅ site.yml 실행 완료"
    else
        log_error "site.yml 실행 실패"
        exit 1
    fi
fi

# label-nodes.yml 실행
log "label-nodes.yml 실행 중... (예상 시간: 2-3분)"
log_info "Kubernetes 노드 라벨링"

if ansible-playbook playbooks/label-nodes.yml -i inventory/hosts.ini 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ label-nodes.yml 실행 완료"
else
    log_error "label-nodes.yml 실행 실패"
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5️⃣ Kubernetes 클러스터 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "5️⃣ Kubernetes 클러스터 확인"

# kubeconfig 복사 (Master 노드에서)
log "kubeconfig 복사 중..."
ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa ubuntu@"$MASTER_IP" \
    "sudo cat /etc/kubernetes/admin.conf" > "$PROJECT_ROOT/kubeconfig.tmp" 2>/dev/null

# Server IP 교체
sed -i.bak "s|https://[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*:6443|https://$MASTER_IP:6443|g" "$PROJECT_ROOT/kubeconfig.tmp"

export KUBECONFIG="$PROJECT_ROOT/kubeconfig.tmp"

# 노드 상태 확인
log "노드 상태 확인 중..."
if kubectl get nodes -o wide 2>&1 | tee -a "$LOG_FILE"; then
    NODE_COUNT=$(kubectl get nodes --no-headers | wc -l | tr -d ' ')
    READY_COUNT=$(kubectl get nodes --no-headers | grep -c " Ready " || echo "0")
    log_info "총 노드: $NODE_COUNT개, Ready: $READY_COUNT개"
    
    if [ "$NODE_COUNT" -eq 14 ] && [ "$READY_COUNT" -eq 14 ]; then
        log "✅ 모든 노드가 Ready 상태입니다"
    else
        log_warn "일부 노드가 Ready 상태가 아닙니다"
    fi
else
    log_error "kubectl 실행 실패"
fi

# Pod 상태 확인
log "Pod 상태 확인 중..."
kubectl get pods -A 2>&1 | tee -a "$LOG_FILE" || true

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5-1️⃣ Ingress 리소스 생성 (ALB 자동 생성)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "5-1️⃣ Ingress 리소스 생성"

# kubeconfig가 설정되어 있는지 확인
if [ -z "$KUBECONFIG" ] || [ ! -f "$KUBECONFIG" ]; then
    log_warn "kubeconfig가 설정되지 않았습니다. Master 노드에서 직접 실행합니다"
    
    # Master 노드에서 Ingress 생성
    log "Master 노드에서 Ingress 생성 중..."
    ssh -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa ubuntu@"$MASTER_IP" << 'INGRESS_EOF'
        # 필요한 Namespace 생성
        kubectl create namespace api --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
        
        # 14-nodes Ingress 파일이 있다면 적용
        if [ -f /home/ubuntu/14-nodes-ingress.yaml ]; then
            kubectl apply -f /home/ubuntu/14-nodes-ingress.yaml
        else
            echo "Ingress 파일을 찾을 수 없습니다. 수동으로 생성하세요."
        fi
INGRESS_EOF
else
    # 로컬에서 Ingress 생성
    log "로컬에서 Ingress 생성 중..."
    
    # 필요한 Namespace 생성
    kubectl create namespace api --dry-run=client -o yaml | kubectl apply -f - 2>&1 | tee -a "$LOG_FILE" || true
    
    # 14-nodes Ingress 적용
    INGRESS_FILE="$PROJECT_ROOT/k8s/ingress/14-nodes-ingress.yaml"
    if [ -f "$INGRESS_FILE" ]; then
        log "14-nodes Ingress 적용 중..."
        if kubectl apply -f "$INGRESS_FILE" 2>&1 | tee -a "$LOG_FILE"; then
            log "✅ Ingress 리소스 생성 완료"
            
            # ALB 생성 대기 (30초)
            log "ALB 생성 대기 중... (30초)"
            sleep 30
            
            # Ingress 상태 확인
            log "Ingress 상태 확인 중..."
            kubectl get ingress -A 2>&1 | tee -a "$LOG_FILE" || true
        else
            log_warn "Ingress 생성 실패 (수동으로 생성 가능)"
        fi
    else
        log_warn "Ingress 파일을 찾을 수 없습니다: $INGRESS_FILE"
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6️⃣ 배포 완료 및 정보 출력
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "6️⃣ 배포 완료"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

log "✅ 14-Node 클러스터 배포 완료!"
log "총 소요 시간: ${MINUTES}분 ${SECONDS}초"
log ""

# 클러스터 정보 출력
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 클러스터 정보${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}Master 노드:${NC}"
echo "  IP: $MASTER_IP"
echo "  SSH: ssh -i ~/.ssh/sesacthon.pem ubuntu@$MASTER_IP"
echo ""
echo -e "${CYAN}VPC:${NC}"
echo "  VPC ID: $VPC_ID"
echo "  Region: $AWS_REGION"
echo ""
echo -e "${CYAN}노드 구성:${NC}"
echo "  총 노드: 14개"
echo "  - Master: 1개 (t3.large, 2 vCPU, 8GB)"
echo "  - API: 7개 (auth, my, scan, character, location, info, chat)"
echo "  - Worker: 2개 (storage, ai)"
echo "  - Infrastructure: 4개 (postgresql, redis, rabbitmq, monitoring)"
echo ""
echo -e "${CYAN}접속 정보:${NC}"
# ALB 주소 확인
ALB_ADDRESS=$(kubectl get ingress -A -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
if [ -n "$ALB_ADDRESS" ]; then
    echo "  ALB 주소: $ALB_ADDRESS"
    echo ""
    echo "  Grafana: http://grafana.growbin.app (또는 http://$ALB_ADDRESS)"
    echo "  ArgoCD: https://argocd.growbin.app (또는 https://$ALB_ADDRESS)"
    echo ""
    echo "  Grafana 비밀번호: admin123"
    echo "  ArgoCD 비밀번호: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
else
    echo "  ALB 생성 중... (3-5분 소요)"
    echo "  확인: kubectl get ingress -A"
fi
echo ""
echo -e "${CYAN}다음 단계:${NC}"
echo "  1. kubectl 설정:"
echo "     export KUBECONFIG=$PROJECT_ROOT/kubeconfig.tmp"
echo ""
echo "  2. ArgoCD 배포:"
echo "     kubectl apply -f argocd/applications/ecoeco-14nodes-appset.yaml"
echo ""
echo "  3. 모니터링 확인:"
echo "     kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring"
echo "     또는 ALB를 통한 접속: http://grafana.growbin.app"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

log "로그 파일: $LOG_FILE"
log "kubeconfig: $PROJECT_ROOT/kubeconfig.tmp"

# 정리
rm -f "$TERRAFORM_DIR/tfplan"
rm -f "$PROJECT_ROOT/kubeconfig.tmp.bak"

log "배포 종료: $(date)"

exit 0

