#!/bin/bash
# Kubernetes 클러스터 검증 스크립트 (Phase 1&2 - 8 nodes)
# 클러스터가 의도대로 구축되었는지 확인

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 결과 추적
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# 로그 파일
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cluster-verification-$(date +%Y%m%d-%H%M%S).log"

# 로그 함수
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

check_pass() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    log "${GREEN}✅ PASS${NC}: $1"
}

check_fail() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    log "${RED}❌ FAIL${NC}: $1"
}

check_warn() {
    log "${YELLOW}⚠️  WARN${NC}: $1"
}

section_header() {
    log ""
    log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${BLUE}$1${NC}"
    log "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log ""
}

# Master 노드 IP 가져오기
get_master_ip() {
    cd "$PROJECT_ROOT/terraform"
    terraform output -raw master_public_ip 2>/dev/null || echo ""
}

# SSH/SSM을 통한 원격 명령 실행
remote_exec() {
    local host=$1
    local cmd=$2
    
    # SSM 방식 시도
    if aws ssm send-command \
        --instance-ids "$host" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=['$cmd']" \
        --region ap-northeast-2 \
        --output text \
        --query 'Command.CommandId' >/dev/null 2>&1; then
        return 0
    else
        # SSH 방식 폴백
        ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 ubuntu@"$host" "$cmd" 2>/dev/null
        return $?
    fi
}

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "🔍 Kubernetes 클러스터 검증 시작"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log ""
log "📅 시작 시간: $(date)"
log "📝 로그 파일: $LOG_FILE"
log ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. AWS 인프라 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "1️⃣ AWS 인프라 검증 (Terraform)"

# 1.1 Terraform 상태 확인
log "1.1 Terraform 상태 확인..."
cd "$PROJECT_ROOT/terraform"

if terraform show >/dev/null 2>&1; then
    check_pass "Terraform state 존재"
else
    check_fail "Terraform state 없음"
fi

# 1.2 EC2 인스턴스 개수 확인 (Phase 1&2: 8 nodes)
log ""
log "1.2 EC2 인스턴스 개수 확인..."

RUNNING_INSTANCES=$(aws ec2 describe-instances \
    --region ap-northeast-2 \
    --filters "Name=tag:Name,Values=k8s-*" \
              "Name=instance-state-name,Values=running" \
    --query 'length(Reservations[*].Instances[*])' \
    --output text)

EXPECTED_NODES=8
if [ "$RUNNING_INSTANCES" -eq "$EXPECTED_NODES" ]; then
    check_pass "EC2 인스턴스 개수: $RUNNING_INSTANCES/$EXPECTED_NODES"
else
    check_fail "EC2 인스턴스 개수 불일치: $RUNNING_INSTANCES/$EXPECTED_NODES (예상)"
fi

# 1.3 SSM Agent 등록 확인
log ""
log "1.3 SSM Agent 등록 확인..."

REGISTERED_SSM=$(aws ssm describe-instance-information \
    --region ap-northeast-2 \
    --filters "Key=tag:Name,Values=k8s-*" \
    --query 'length(InstanceInformationList[?PingStatus==`Online`])' \
    --output text 2>/dev/null || echo "0")

if [ "$REGISTERED_SSM" -eq "$EXPECTED_NODES" ]; then
    check_pass "SSM Agent 등록: $REGISTERED_SSM/$EXPECTED_NODES"
else
    check_warn "SSM Agent 일부 미등록: $REGISTERED_SSM/$EXPECTED_NODES"
fi

# 1.4 VPC 및 네트워크 확인
log ""
log "1.4 VPC 및 네트워크 확인..."

VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
if [ -n "$VPC_ID" ]; then
    check_pass "VPC 생성: $VPC_ID"
else
    check_fail "VPC 없음"
fi

# 1.5 Security Groups 확인
log ""
log "1.5 Security Groups 확인..."

MASTER_SG=$(terraform output -json security_group_ids 2>/dev/null | jq -r '.master' || echo "")
WORKER_SG=$(terraform output -json security_group_ids 2>/dev/null | jq -r '.worker' || echo "")

if [ -n "$MASTER_SG" ] && [ -n "$WORKER_SG" ]; then
    check_pass "Security Groups 생성 (Master: $MASTER_SG, Worker: $WORKER_SG)"
else
    check_fail "Security Groups 누락"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Kubernetes 클러스터 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "2️⃣ Kubernetes 클러스터 검증"

MASTER_IP=$(get_master_ip)

if [ -z "$MASTER_IP" ]; then
    check_fail "Master IP를 찾을 수 없음"
    log ""
    log "${RED}❌ Master 노드에 접근할 수 없어 Kubernetes 검증을 건너뜁니다.${NC}"
else
    log "Master IP: $MASTER_IP"
    log ""

    # 2.1 노드 개수 확인
    log "2.1 노드 개수 확인..."
    
    NODE_COUNT=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@"$MASTER_IP" \
        "kubectl get nodes --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$NODE_COUNT" -eq "$EXPECTED_NODES" ]; then
        check_pass "Kubernetes 노드 개수: $NODE_COUNT/$EXPECTED_NODES"
    else
        check_fail "Kubernetes 노드 개수 불일치: $NODE_COUNT/$EXPECTED_NODES"
    fi

    # 2.2 노드 Ready 상태 확인
    log ""
    log "2.2 노드 Ready 상태 확인..."
    
    READY_NODES=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get nodes --no-headers 2>/dev/null | grep -c ' Ready ' || echo '0'" 2>/dev/null)
    
    if [ "$READY_NODES" -eq "$EXPECTED_NODES" ]; then
        check_pass "모든 노드 Ready: $READY_NODES/$EXPECTED_NODES"
    else
        check_fail "일부 노드 Not Ready: $READY_NODES/$EXPECTED_NODES"
        
        # 상세 노드 상태 출력
        log ""
        log "노드 상태 상세:"
        ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
            "kubectl get nodes -o wide" 2>/dev/null | while read line; do
            log "  $line"
        done
    fi

    # 2.3 노드 레이블 확인
    log ""
    log "2.3 노드 레이블 확인..."
    
    # Master 노드
    MASTER_LABEL=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get nodes -l node-role.kubernetes.io/control-plane --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$MASTER_LABEL" -eq 1 ]; then
        check_pass "Master 노드 레이블: 1개"
    else
        check_fail "Master 노드 레이블 누락"
    fi
    
    # API 노드 (Phase 1&2: 5개)
    API_NODES=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get nodes -l workload=api --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$API_NODES" -eq 5 ]; then
        check_pass "API 노드 레이블: 5개 (auth, my, scan, character, location)"
    else
        check_fail "API 노드 레이블 불일치: $API_NODES/5"
    fi
    
    # Infrastructure 노드 (2개: PostgreSQL, Redis)
    INFRA_NODES=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get nodes -l 'workload in (database,cache)' --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$INFRA_NODES" -eq 2 ]; then
        check_pass "Infrastructure 노드 레이블: 2개 (PostgreSQL, Redis)"
    else
        check_fail "Infrastructure 노드 레이블 불일치: $INFRA_NODES/2"
    fi

    # 2.4 CNI 플러그인 확인 (Calico)
    log ""
    log "2.4 CNI 플러그인 확인..."
    
    CALICO_PODS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get pods -n kube-system -l k8s-app=calico-node --no-headers 2>/dev/null | grep -c Running || echo '0'" 2>/dev/null)
    
    if [ "$CALICO_PODS" -eq "$EXPECTED_NODES" ]; then
        check_pass "Calico CNI 실행 중: $CALICO_PODS/$EXPECTED_NODES pods"
    else
        check_fail "Calico CNI 일부 미실행: $CALICO_PODS/$EXPECTED_NODES"
    fi

    # 2.5 CoreDNS 확인
    log ""
    log "2.5 CoreDNS 확인..."
    
    COREDNS_PODS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get pods -n kube-system -l k8s-app=kube-dns --no-headers 2>/dev/null | grep -c Running || echo '0'" 2>/dev/null)
    
    if [ "$COREDNS_PODS" -ge 2 ]; then
        check_pass "CoreDNS 실행 중: $COREDNS_PODS pods"
    else
        check_fail "CoreDNS 미실행 또는 부족: $COREDNS_PODS pods"
    fi

    # 2.6 Kubernetes 시스템 Pod 확인
    log ""
    log "2.6 Kubernetes 시스템 Pod 확인..."
    
    SYSTEM_PODS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get pods -n kube-system --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$SYSTEM_PODS" -gt 10 ]; then
        check_pass "시스템 Pod 실행 중: $SYSTEM_PODS개"
    else
        check_fail "시스템 Pod 부족: $SYSTEM_PODS개"
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. GitOps (ArgoCD) 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "3️⃣ GitOps (ArgoCD) 검증"

if [ -z "$MASTER_IP" ]; then
    log "${YELLOW}⚠️  Master IP 없음 - ArgoCD 검증 건너뜀${NC}"
else
    # 3.1 ArgoCD Namespace 확인
    log "3.1 ArgoCD Namespace 확인..."
    
    ARGOCD_NS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get namespace argocd --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$ARGOCD_NS" -eq 1 ]; then
        check_pass "ArgoCD Namespace 존재"
    else
        check_fail "ArgoCD Namespace 없음"
    fi

    # 3.2 ArgoCD Pod 상태 확인
    log ""
    log "3.2 ArgoCD Pod 상태 확인..."
    
    ARGOCD_PODS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get pods -n argocd --no-headers 2>/dev/null | grep -c Running || echo '0'" 2>/dev/null)
    
    if [ "$ARGOCD_PODS" -ge 5 ]; then
        check_pass "ArgoCD Pods 실행 중: $ARGOCD_PODS개"
    else
        check_fail "ArgoCD Pods 부족 또는 미실행: $ARGOCD_PODS개"
    fi

    # 3.3 ArgoCD Server Service 확인
    log ""
    log "3.3 ArgoCD Server Service 확인..."
    
    ARGOCD_SVC=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get svc argocd-server -n argocd --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$ARGOCD_SVC" -eq 1 ]; then
        check_pass "ArgoCD Server Service 존재"
    else
        check_fail "ArgoCD Server Service 없음"
    fi

    # 3.4 ArgoCD Application 확인
    log ""
    log "3.4 ArgoCD Application 확인..."
    
    # ecoeco-backend-phase12 애플리케이션 확인
    ARGOCD_APP=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get application ecoeco-backend-phase12 -n argocd --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$ARGOCD_APP" -eq 1 ]; then
        check_pass "ArgoCD Application 존재: ecoeco-backend-phase12"
        
        # Application 상태 확인
        APP_STATUS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
            "kubectl get application ecoeco-backend-phase12 -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null" || echo "Unknown")
        
        if [ "$APP_STATUS" = "Synced" ]; then
            check_pass "Application Sync 상태: Synced"
        else
            check_warn "Application Sync 상태: $APP_STATUS (예상: Synced)"
        fi
    else
        check_fail "ArgoCD Application 없음: ecoeco-backend-phase12"
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 네임스페이스 및 리소스 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "4️⃣ 네임스페이스 및 리소스 검증"

if [ -z "$MASTER_IP" ]; then
    log "${YELLOW}⚠️  Master IP 없음 - 리소스 검증 건너뜀${NC}"
else
    # 4.1 필수 Namespace 확인
    log "4.1 필수 Namespace 확인..."
    
    REQUIRED_NS=("default" "kube-system" "argocd")
    for ns in "${REQUIRED_NS[@]}"; do
        NS_EXISTS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
            "kubectl get namespace $ns --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
        
        if [ "$NS_EXISTS" -eq 1 ]; then
            check_pass "Namespace 존재: $ns"
        else
            check_fail "Namespace 없음: $ns"
        fi
    done

    # 4.2 ConfigMap 확인
    log ""
    log "4.2 ConfigMap 확인..."
    
    CONFIGMAPS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get configmap -n default --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    log "ConfigMap 개수: $CONFIGMAPS개"

    # 4.3 Secret 확인
    log ""
    log "4.3 Secret 확인..."
    
    SECRETS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get secret -n default --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    log "Secret 개수: $SECRETS개"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 네트워크 및 DNS 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "5️⃣ 네트워크 및 DNS 검증"

if [ -z "$MASTER_IP" ]; then
    log "${YELLOW}⚠️  Master IP 없음 - 네트워크 검증 건너뜀${NC}"
else
    # 5.1 Pod 네트워크 확인 (Calico VXLAN)
    log "5.1 Pod 네트워크 확인..."
    
    POD_CIDR=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl cluster-info dump 2>/dev/null | grep -oP 'pod-network-cidr=\K[0-9./]+' | head -1" 2>/dev/null || echo "")
    
    if [ -n "$POD_CIDR" ]; then
        check_pass "Pod 네트워크 CIDR: $POD_CIDR"
    else
        check_warn "Pod 네트워크 CIDR 확인 불가"
    fi

    # 5.2 Service 네트워크 확인
    log ""
    log "5.2 Service 네트워크 확인..."
    
    SVC_CIDR=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl cluster-info dump 2>/dev/null | grep -oP 'service-cluster-ip-range=\K[0-9./]+' | head -1" 2>/dev/null || echo "")
    
    if [ -n "$SVC_CIDR" ]; then
        check_pass "Service 네트워크 CIDR: $SVC_CIDR"
    else
        check_warn "Service 네트워크 CIDR 확인 불가"
    fi

    # 5.3 DNS 해석 테스트
    log ""
    log "5.3 Kubernetes DNS 해석 테스트..."
    
    DNS_TEST=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl run dns-test --image=busybox:1.28 --restart=Never --rm -i --command -- nslookup kubernetes.default 2>/dev/null | grep -c 'Server:' || echo '0'" 2>/dev/null)
    
    if [ "$DNS_TEST" -gt 0 ]; then
        check_pass "Kubernetes DNS 해석 작동"
    else
        check_warn "Kubernetes DNS 해석 테스트 실패 (Pod가 실행 중이지 않을 수 있음)"
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 최종 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "📊 검증 결과 요약"

log "총 검사 항목: $TOTAL_CHECKS"
log "${GREEN}통과: $PASSED_CHECKS${NC}"
log "${RED}실패: $FAILED_CHECKS${NC}"
log ""

SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
log "성공률: ${SUCCESS_RATE}%"
log ""

if [ "$FAILED_CHECKS" -eq 0 ]; then
    log "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${GREEN}✅ 모든 검증 통과!${NC}"
    log "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=0
elif [ "$SUCCESS_RATE" -ge 80 ]; then
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${YELLOW}⚠️  일부 항목 실패 (${SUCCESS_RATE}% 성공)${NC}"
    log "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=0
else
    log "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${RED}❌ 다수 항목 실패 (${SUCCESS_RATE}% 성공)${NC}"
    log "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=1
fi

log ""
log "📅 종료 시간: $(date)"
log "📝 상세 로그: $LOG_FILE"
log ""

exit $EXIT_CODE

