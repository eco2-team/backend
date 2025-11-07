#!/bin/bash
# GitOps 파이프라인 검증 스크립트
# GitHub Actions + ArgoCD + Helm 통합 확인

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 결과 추적
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# 로그 함수
check_pass() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

check_fail() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    echo -e "${RED}❌ FAIL${NC}: $1"
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

section_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Master IP 가져오기
get_master_ip() {
    cd "$PROJECT_ROOT/terraform"
    terraform output -raw master_public_ip 2>/dev/null || echo ""
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 GitOps 파이프라인 검증"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📅 시작 시간: $(date)"
echo ""

MASTER_IP=$(get_master_ip)

if [ -z "$MASTER_IP" ]; then
    echo -e "${RED}❌ Master IP를 찾을 수 없습니다.${NC}"
    exit 1
fi

echo "Master IP: $MASTER_IP"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. GitHub Repository 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "1️⃣ GitHub Repository 검증"

# 1.1 Git Remote 확인
echo "1.1 Git Remote 확인..."

cd "$PROJECT_ROOT"
GIT_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")

if [[ "$GIT_REMOTE" =~ github\.com ]]; then
    check_pass "GitHub Repository 연결: $GIT_REMOTE"
else
    check_fail "GitHub Repository 미연결"
fi

# 1.2 현재 브랜치 확인
echo ""
echo "1.2 현재 브랜치 확인..."

CURRENT_BRANCH=$(git branch --show-current)
echo "현재 브랜치: $CURRENT_BRANCH"

# 1.3 GitHub Actions Workflow 파일 확인
echo ""
echo "1.3 GitHub Actions Workflow 파일 확인..."

WORKFLOW_FILE="$PROJECT_ROOT/.github/workflows/api-build.yml"
if [ -f "$WORKFLOW_FILE" ]; then
    check_pass "GitHub Actions Workflow 존재: api-build.yml"
else
    check_fail "GitHub Actions Workflow 없음"
fi

# 1.4 Helm Chart 확인
echo ""
echo "1.4 Helm Chart 확인..."

HELM_CHART="$PROJECT_ROOT/charts/ecoeco-backend/Chart.yaml"
if [ -f "$HELM_CHART" ]; then
    check_pass "Helm Chart 존재: ecoeco-backend"
    
    CHART_VERSION=$(grep '^version:' "$HELM_CHART" | awk '{print $2}')
    echo "   Chart Version: $CHART_VERSION"
else
    check_fail "Helm Chart 없음"
fi

# 1.5 ArgoCD Application Manifest 확인
echo ""
echo "1.5 ArgoCD Application Manifest 확인..."

ARGOCD_APP="$PROJECT_ROOT/argocd/applications/ecoeco-backend-phase12.yaml"
if [ -f "$ARGOCD_APP" ]; then
    check_pass "ArgoCD Application Manifest 존재: ecoeco-backend-phase12.yaml"
else
    check_fail "ArgoCD Application Manifest 없음"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ArgoCD 설치 및 구성 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "2️⃣ ArgoCD 설치 및 구성 검증"

# 2.1 ArgoCD Namespace
echo "2.1 ArgoCD Namespace 확인..."

ARGOCD_NS=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@"$MASTER_IP" \
    "kubectl get namespace argocd --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")

if [ "$ARGOCD_NS" -eq 1 ]; then
    check_pass "ArgoCD Namespace 존재"
else
    check_fail "ArgoCD Namespace 없음"
    echo ""
    echo -e "${RED}❌ ArgoCD가 설치되지 않았습니다. 검증을 중단합니다.${NC}"
    exit 1
fi

# 2.2 ArgoCD Pods 상태
echo ""
echo "2.2 ArgoCD Pods 상태 확인..."

ARGOCD_PODS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get pods -n argocd --no-headers 2>/dev/null")

echo "ArgoCD Pods:"
echo "$ARGOCD_PODS" | while read line; do
    echo "  $line"
done

RUNNING_PODS=$(echo "$ARGOCD_PODS" | grep -c "Running" || echo "0")
TOTAL_ARGOCD_PODS=$(echo "$ARGOCD_PODS" | wc -l)

if [ "$RUNNING_PODS" -ge 5 ]; then
    check_pass "ArgoCD Pods 실행 중: $RUNNING_PODS/$TOTAL_ARGOCD_PODS"
else
    check_fail "ArgoCD Pods 일부 미실행: $RUNNING_PODS/$TOTAL_ARGOCD_PODS"
fi

# 2.3 ArgoCD Server Service
echo ""
echo "2.3 ArgoCD Server Service 확인..."

ARGOCD_SVC=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get svc argocd-server -n argocd --no-headers 2>/dev/null")

if [ -n "$ARGOCD_SVC" ]; then
    check_pass "ArgoCD Server Service 존재"
    echo "  $ARGOCD_SVC"
else
    check_fail "ArgoCD Server Service 없음"
fi

# 2.4 ArgoCD Admin 비밀번호 확인
echo ""
echo "2.4 ArgoCD Admin 비밀번호 확인..."

ARGOCD_PWD=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' 2>/dev/null | base64 -d" 2>/dev/null || echo "")

if [ -n "$ARGOCD_PWD" ]; then
    check_pass "ArgoCD Admin 비밀번호 확인 가능"
    echo "  비밀번호: $ARGOCD_PWD"
else
    check_warn "ArgoCD Admin 비밀번호 Secret 없음 (이미 변경되었을 수 있음)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ArgoCD Application 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "3️⃣ ArgoCD Application 검증"

# 3.1 Application 존재 확인
echo "3.1 ArgoCD Application 목록..."

APPS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get applications -n argocd --no-headers 2>/dev/null")

if [ -n "$APPS" ]; then
    echo "Applications:"
    echo "$APPS" | while read line; do
        echo "  $line"
    done
    
    APP_COUNT=$(echo "$APPS" | wc -l)
    check_pass "ArgoCD Applications: $APP_COUNT개"
else
    check_fail "ArgoCD Applications 없음"
fi

# 3.2 ecoeco-backend-phase12 Application 상세
echo ""
echo "3.2 ecoeco-backend-phase12 Application 상세..."

APP_EXISTS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get application ecoeco-backend-phase12 -n argocd --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")

if [ "$APP_EXISTS" -eq 1 ]; then
    check_pass "Application 존재: ecoeco-backend-phase12"
    
    # Sync 상태
    SYNC_STATUS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get application ecoeco-backend-phase12 -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null" || echo "Unknown")
    
    # Health 상태
    HEALTH_STATUS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get application ecoeco-backend-phase12 -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null" || echo "Unknown")
    
    echo "  Sync Status: $SYNC_STATUS"
    echo "  Health Status: $HEALTH_STATUS"
    
    if [ "$SYNC_STATUS" = "Synced" ]; then
        check_pass "Application Sync: Synced"
    else
        check_warn "Application Sync: $SYNC_STATUS (예상: Synced)"
    fi
    
    if [ "$HEALTH_STATUS" = "Healthy" ]; then
        check_pass "Application Health: Healthy"
    else
        check_warn "Application Health: $HEALTH_STATUS (예상: Healthy)"
    fi
else
    check_fail "Application 없음: ecoeco-backend-phase12"
fi

# 3.3 Application Source Repository
echo ""
echo "3.3 Application Source Repository 확인..."

APP_REPO=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get application ecoeco-backend-phase12 -n argocd -o jsonpath='{.spec.source.repoURL}' 2>/dev/null" || echo "")

if [[ "$APP_REPO" =~ github\.com/SeSACTHON/backend ]]; then
    check_pass "Source Repository: $APP_REPO"
else
    check_warn "Source Repository 확인 불가 또는 불일치: $APP_REPO"
fi

# 3.4 Application Target Namespace
echo ""
echo "3.4 Application Target Namespace 확인..."

TARGET_NS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get application ecoeco-backend-phase12 -n argocd -o jsonpath='{.spec.destination.namespace}' 2>/dev/null" || echo "")

echo "  Target Namespace: $TARGET_NS"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Helm Release 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "4️⃣ Helm Release 검증"

# 4.1 Helm Releases 확인
echo "4.1 Helm Releases 확인..."

HELM_RELEASES=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "helm list -A 2>/dev/null" || echo "")

if [ -n "$HELM_RELEASES" ]; then
    echo "Helm Releases:"
    echo "$HELM_RELEASES" | while read line; do
        echo "  $line"
    done
else
    check_warn "Helm Releases 없음 (ArgoCD가 직접 관리하는 경우 정상)"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 배포된 리소스 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "5️⃣ 배포된 리소스 검증"

# 5.1 API Deployments (Phase 1&2)
echo "5.1 API Deployments 확인 (Phase 1&2)..."

API_SERVICES=("auth-api" "my-api" "scan-api" "character-api" "location-api")

for api in "${API_SERVICES[@]}"; do
    DEPLOY_EXISTS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get deployment $api -n default --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$DEPLOY_EXISTS" -eq 1 ]; then
        READY=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
            "kubectl get deployment $api -n default -o jsonpath='{.status.readyReplicas}' 2>/dev/null" || echo "0")
        DESIRED=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
            "kubectl get deployment $api -n default -o jsonpath='{.spec.replicas}' 2>/dev/null" || echo "0")
        
        if [ "$READY" -eq "$DESIRED" ] && [ "$READY" -gt 0 ]; then
            check_pass "Deployment: $api ($READY/$DESIRED pods ready)"
        else
            check_warn "Deployment: $api ($READY/$DESIRED pods ready)"
        fi
    else
        check_warn "Deployment 없음: $api (아직 배포되지 않았을 수 있음)"
    fi
done

# 5.2 Services 확인
echo ""
echo "5.2 Services 확인..."

for api in "${API_SERVICES[@]}"; do
    SVC_EXISTS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
        "kubectl get svc $api -n default --no-headers 2>/dev/null | wc -l" 2>/dev/null || echo "0")
    
    if [ "$SVC_EXISTS" -eq 1 ]; then
        check_pass "Service 존재: $api"
    else
        check_warn "Service 없음: $api"
    fi
done

# 5.3 Ingress 확인
echo ""
echo "5.3 Ingress 확인..."

INGRESS=$(ssh -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get ingress -n default --no-headers 2>/dev/null")

if [ -n "$INGRESS" ]; then
    echo "Ingress:"
    echo "$INGRESS" | while read line; do
        echo "  $line"
    done
    
    INGRESS_COUNT=$(echo "$INGRESS" | wc -l)
    check_pass "Ingress: $INGRESS_COUNT개"
else
    check_warn "Ingress 없음"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. GitHub Actions 검증 (선택)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "6️⃣ GitHub Actions 검증"

echo "GitHub Actions는 GitHub 웹 인터페이스에서 확인하세요:"
echo "  https://github.com/SeSACTHON/backend/actions"
echo ""

# GITHUB_TOKEN이 설정되어 있으면 최근 워크플로우 확인
if [ -n "$GITHUB_TOKEN" ]; then
    echo "6.1 최근 Workflow Runs 확인..."
    
    RECENT_RUNS=$(gh run list --repo SeSACTHON/backend --limit 5 2>/dev/null || echo "")
    
    if [ -n "$RECENT_RUNS" ]; then
        echo "최근 5개 Workflow Runs:"
        echo "$RECENT_RUNS"
        check_pass "GitHub API 연결 성공"
    else
        check_warn "GitHub API 연결 실패 또는 권한 부족"
    fi
else
    check_warn "GITHUB_TOKEN 미설정 - GitHub Actions 상태 확인 불가"
    echo "  GitHub Token 설정 방법:"
    echo "    export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 최종 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
section_header "📊 GitOps 검증 결과 요약"

echo "총 검사 항목: $TOTAL_CHECKS"
echo -e "${GREEN}통과: $PASSED_CHECKS${NC}"
echo -e "${RED}실패: $FAILED_CHECKS${NC}"
echo ""

if [ "$TOTAL_CHECKS" -gt 0 ]; then
    SUCCESS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
    echo "성공률: ${SUCCESS_RATE}%"
else
    SUCCESS_RATE=0
    echo "성공률: N/A"
fi
echo ""

if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✅ GitOps 파이프라인 정상 작동${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=0
elif [ "$SUCCESS_RATE" -ge 70 ]; then
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}⚠️  일부 항목 미구성 (${SUCCESS_RATE}% 성공)${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}❌ GitOps 파이프라인 구성 불완전 (${SUCCESS_RATE}% 성공)${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    EXIT_CODE=1
fi

echo ""
echo "📅 종료 시간: $(date)"
echo ""

## ArgoCD 접속 정보
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔗 ArgoCD 접속 정보"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "ArgoCD URL: https://argocd.growbin.app"
echo "Username: admin"
if [ -n "$ARGOCD_PWD" ]; then
    echo "Password: $ARGOCD_PWD"
else
    echo "Password: (Secret에서 확인 필요)"
fi
echo ""

exit $EXIT_CODE

