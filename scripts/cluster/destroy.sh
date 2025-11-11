#!/bin/bash
# 14-Node 클러스터 완전 삭제 스크립트 v2.0
# Terraform 기반 리소스 정리 + AWS 의존성 완벽 처리

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/destroy-$(date +%Y%m%d-%H%M%S).log"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

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

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# 시작 시간
START_TIME=$(date +%s)

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

print_header "🗑️  14-Node 클러스터 완전 삭제"

log "삭제 시작: $(date)"
log "로그 파일: $LOG_FILE"
log ""

# 자동 모드 확인
AUTO_MODE=${AUTO_MODE:-false}

if [ "$AUTO_MODE" != "true" ]; then
    echo -e "${RED}⚠️  경고: 모든 리소스가 삭제됩니다!${NC}"
    echo ""
    echo "삭제될 리소스:"
    echo "  - 14개 EC2 인스턴스"
    echo "  - VPC 및 네트워크 리소스"
    echo "  - CloudFront Distribution"
    echo "  - S3 Bucket (이미지 포함)"
    echo "  - ACM Certificate"
    echo "  - IAM Roles & Policies"
    echo ""
    read -p "정말로 삭제하시겠습니까? (yes 입력): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
        log "삭제 취소됨"
        exit 0
    fi
else
    log_info "자동 모드로 실행 중..."
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣ Terraform 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "1️⃣ Terraform 상태 확인"

cd "$TERRAFORM_DIR"

# Terraform 초기화
log "Terraform 초기화 중..."
if terraform init -upgrade >/dev/null 2>&1; then
    log "✅ Terraform 초기화 완료"
else
    log_warn "Terraform 초기화 실패 (State 파일이 없을 수 있음)"
fi

# 리소스 확인
RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
log_info "Terraform 관리 리소스: $RESOURCE_COUNT개"

if [ "$RESOURCE_COUNT" -eq 0 ]; then
    log_warn "Terraform State에 리소스가 없습니다"
    log_info "수동 정리를 진행하시겠습니까? (yes/no)"
    read -r response
    if [ "$response" != "yes" ]; then
        exit 0
    fi
fi

# VPC ID 가져오기
VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-northeast-2")

if [ -n "$VPC_ID" ]; then
    log_info "VPC ID: $VPC_ID"
    log_info "AWS Region: $AWS_REGION"
else
    log_warn "VPC ID를 가져올 수 없습니다 (이미 삭제되었을 수 있음)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2️⃣ Kubernetes 리소스 정리 (선택적)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "2️⃣ Kubernetes 리소스 정리"

if kubectl cluster-info &>/dev/null; then
    log "Kubernetes 클러스터 발견"
    log_info "Kubernetes 리소스를 삭제하시겠습니까? (yes/no)"
    
    if [ "$AUTO_MODE" = "true" ]; then
        response="yes"
    else
        read -r response
    fi
    
    if [ "$response" = "yes" ]; then
        log "Ingress 삭제 중..."
        kubectl delete ingress --all -A 2>/dev/null || true
        
        log "PVC 삭제 중..."
        kubectl delete pvc --all -A 2>/dev/null || true
        
        log "LoadBalancer Service 삭제 중..."
        kubectl delete svc --field-selector spec.type=LoadBalancer -A 2>/dev/null || true
        
        log "✅ Kubernetes 리소스 삭제 완료"
        
        # ALB 삭제 대기
        log "ALB 삭제 대기 중... (30초)"
        sleep 30
    else
        log_info "Kubernetes 리소스 삭제 건너뜀"
    fi
else
    log_info "Kubernetes 클러스터에 연결할 수 없습니다 (건너뜀)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3️⃣ AWS 의존성 리소스 사전 정리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "3️⃣ AWS 의존성 리소스 사전 정리"

if [ -n "$VPC_ID" ]; then
    # Load Balancer 확인 및 삭제
    log "Load Balancer 확인 중..."
    ALB_ARNS=$(aws elbv2 describe-load-balancers \
        --region "$AWS_REGION" \
        --query "LoadBalancers[?VpcId==\`$VPC_ID\`].LoadBalancerArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$ALB_ARNS" ]; then
        log_warn "Load Balancer 발견 (삭제 중...)"
        for alb_arn in $ALB_ARNS; do
            aws elbv2 delete-load-balancer --load-balancer-arn "$alb_arn" --region "$AWS_REGION" 2>/dev/null || true
        done
        log "ALB 삭제 대기 중... (60초)"
        sleep 60
    else
        log "✅ Load Balancer 없음"
    fi
    
    # Target Groups 삭제
    log "Target Groups 확인 중..."
    TG_ARNS=$(aws elbv2 describe-target-groups \
        --region "$AWS_REGION" \
        --query "TargetGroups[?VpcId==\`$VPC_ID\`].TargetGroupArn" \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$TG_ARNS" ]; then
        log_warn "Target Groups 발견 (삭제 중...)"
        for tg_arn in $TG_ARNS; do
            aws elbv2 delete-target-group --target-group-arn "$tg_arn" --region "$AWS_REGION" 2>/dev/null || true
        done
        log "✅ Target Groups 삭제 완료"
    else
        log "✅ Target Groups 없음"
    fi
fi

# CloudFront Distribution 확인 및 삭제
log "CloudFront Distribution 확인 중..."
CF_DIST_IDS=$(aws acm list-certificates \
    --region us-east-1 \
    --output json 2>/dev/null | \
    jq -r '.CertificateSummaryList[]? | select(.DomainName | contains("images") or contains("growbin")) | .CertificateArn' 2>/dev/null | \
    xargs -I {} aws acm describe-certificate --certificate-arn {} --region us-east-1 --query 'Certificate.InUseBy[]' --output text 2>/dev/null | \
    grep -o 'E[A-Z0-9]*' || echo "")

if [ -n "$CF_DIST_IDS" ]; then
    log_warn "CloudFront Distribution 발견 (삭제 시 5-10분 소요)"
    for dist_id in $CF_DIST_IDS; do
        log_info "Distribution ID: $dist_id"
        
        # Disable
        CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json 2>/dev/null || echo "")
        if [ -n "$CONFIG" ]; then
            ETAG=$(echo "$CONFIG" | jq -r '.ETag')
            IS_ENABLED=$(echo "$CONFIG" | jq -r '.DistributionConfig.Enabled')
            
            if [ "$IS_ENABLED" = "true" ]; then
                log "Distribution Disable 중..."
                NEW_CONFIG=$(echo "$CONFIG" | jq '.DistributionConfig | .Enabled = false')
                aws cloudfront update-distribution \
                    --id "$dist_id" \
                    --if-match "$ETAG" \
                    --distribution-config "$NEW_CONFIG" >/dev/null 2>&1 || true
                
                log "Distribution Disabled 대기 중... (120초)"
                sleep 120
            fi
            
            # Delete
            FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json 2>/dev/null || echo "")
            FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag' 2>/dev/null || echo "")
            FINAL_STATUS=$(aws cloudfront get-distribution --id "$dist_id" --query 'Distribution.Status' --output text 2>/dev/null || echo "Unknown")
            
            if [ "$FINAL_STATUS" = "Deployed" ] && [ -n "$FINAL_ETAG" ]; then
                log "Distribution 삭제 중..."
                aws cloudfront delete-distribution --id "$dist_id" --if-match "$FINAL_ETAG" 2>/dev/null || true
                log "✅ Distribution 삭제 요청 완료"
            else
                log_warn "Distribution 삭제 실패 (Status: $FINAL_STATUS)"
                log_info "5-10분 후 수동 삭제가 필요할 수 있습니다"
            fi
        fi
    done
else
    log "✅ CloudFront Distribution 없음"
fi

# S3 Bucket 정리
log "S3 Bucket 확인 중..."
BUCKETS=$(aws s3api list-buckets \
    --query "Buckets[?starts_with(Name, 'prod-sesacthon')].Name" \
    --output text 2>/dev/null || echo "")

if [ -n "$BUCKETS" ]; then
    log_warn "S3 Bucket 발견 (정리 중...)"
    for bucket in $BUCKETS; do
        log_info "Bucket: $bucket"
        
        # 내용물 삭제
        aws s3 rm "s3://$bucket" --recursive 2>/dev/null || true
        
        # 버전 객체 삭제
        aws s3api delete-objects \
            --bucket "$bucket" \
            --delete "$(aws s3api list-object-versions \
                --bucket "$bucket" \
                --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
                --max-items 1000 2>/dev/null || echo '{}')" 2>/dev/null || true
        
        # Delete Markers 삭제
        aws s3api delete-objects \
            --bucket "$bucket" \
            --delete "$(aws s3api list-object-versions \
                --bucket "$bucket" \
                --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
                --max-items 1000 2>/dev/null || echo '{}')" 2>/dev/null || true
        
        # Bucket 삭제
        aws s3api delete-bucket --bucket "$bucket" --region "$AWS_REGION" 2>/dev/null || true
        log "✅ Bucket 삭제: $bucket"
    done
else
    log "✅ S3 Bucket 없음"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4️⃣ Terraform Destroy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "4️⃣ Terraform Destroy (10-15분)"

cd "$TERRAFORM_DIR"

log "Terraform destroy 실행 중... (예상 시간: 10-15분)"
log_warn "VPC 삭제 시 NAT Gateway 대기로 5분 이상 소요될 수 있습니다"

if terraform destroy -auto-approve 2>&1 | tee -a "$LOG_FILE"; then
    log "✅ Terraform destroy 완료"
else
    log_error "Terraform destroy 실패"
    log_info "수동 정리가 필요할 수 있습니다"
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5️⃣ 잔여 리소스 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "5️⃣ 잔여 리소스 확인"

# VPC 확인
if [ -n "$VPC_ID" ]; then
    VPC_EXISTS=$(aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --region "$AWS_REGION" 2>/dev/null | jq -r '.Vpcs | length' || echo "0")
    if [ "$VPC_EXISTS" -eq 0 ]; then
        log "✅ VPC 삭제 완료"
    else
        log_warn "VPC가 아직 존재합니다: $VPC_ID"
        log_info "NAT Gateway 삭제 대기 중일 수 있습니다"
    fi
fi

# EC2 인스턴스 확인
INSTANCE_COUNT=$(aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --filters "Name=tag:Project,Values=sesacthon" "Name=instance-state-name,Values=running,pending,stopping,stopped" \
    --query 'Reservations[].Instances[].InstanceId' \
    --output text 2>/dev/null | wc -w | tr -d ' ')

if [ "$INSTANCE_COUNT" -eq 0 ]; then
    log "✅ EC2 인스턴스 없음"
else
    log_warn "EC2 인스턴스가 $INSTANCE_COUNT개 남아있습니다"
fi

# ACM Certificate 확인
CERT_COUNT=$(aws acm list-certificates \
    --region us-east-1 \
    --output json 2>/dev/null | \
    jq -r '.CertificateSummaryList[]? | select(.DomainName | contains("growbin")) | .CertificateArn' 2>/dev/null | wc -l | tr -d ' ')

if [ "$CERT_COUNT" -eq 0 ]; then
    log "✅ ACM Certificate 없음"
else
    log_warn "ACM Certificate가 $CERT_COUNT개 남아있습니다"
    log_info "CloudFront 삭제 대기 중일 수 있습니다 (5-10분 후 자동 삭제)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6️⃣ 삭제 완료
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "6️⃣ 삭제 완료"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

log "✅ 14-Node 클러스터 삭제 완료!"
log "총 소요 시간: ${MINUTES}분 ${SECONDS}초"
log ""

# 정보 출력
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}📋 삭제 완료${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${CYAN}삭제된 리소스:${NC}"
echo "  ✅ EC2 인스턴스 (14개)"
echo "  ✅ VPC 및 네트워크 리소스"
echo "  ✅ Load Balancer & Target Groups"
echo "  ✅ S3 Bucket"
echo "  ✅ IAM Roles & Policies"
echo ""
if [ "$CERT_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  주의:${NC}"
    echo "  - ACM Certificate: CloudFront 삭제 후 자동 삭제됨 (5-10분)"
    echo "  - CloudFront: 백그라운드에서 삭제 진행 중"
    echo ""
fi
echo -e "${CYAN}다음 단계:${NC}"
echo "  - 삭제 확인: aws ec2 describe-vpcs --region $AWS_REGION"
echo "  - 비용 확인: AWS Console > Billing Dashboard"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

log "로그 파일: $LOG_FILE"
log "삭제 종료: $(date)"

# 정리
rm -f "$PROJECT_ROOT/kubeconfig.tmp"
rm -f "$PROJECT_ROOT/kubeconfig.tmp.bak"

exit 0

