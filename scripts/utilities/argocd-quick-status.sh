#!/bin/bash
# ArgoCD 배포 상태 빠른 확인 스크립트
# 
# 사용법:
#   ./scripts/utilities/argocd-quick-status.sh

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ArgoCD 설치 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "1️⃣ ArgoCD 설치 확인"

if ! kubectl get namespace argocd &>/dev/null; then
    echo -e "${RED}❌ ArgoCD namespace가 없습니다${NC}"
    echo "   ArgoCD를 먼저 설치하세요:"
    echo "   kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml"
    exit 1
fi

ARGOCD_PODS=$(kubectl get pods -n argocd --no-headers 2>/dev/null | wc -l | tr -d ' ')
ARGOCD_READY=$(kubectl get pods -n argocd --no-headers 2>/dev/null | grep -E "Running|Completed" | wc -l | tr -d ' ')

echo -e "${GREEN}✅ ArgoCD Namespace: 존재${NC}"
echo "   Pod 상태: $ARGOCD_READY/$ARGOCD_PODS Ready"

if [ "$ARGOCD_READY" -lt "$ARGOCD_PODS" ]; then
    echo -e "${YELLOW}⚠️  일부 Pod가 아직 Ready가 아닙니다${NC}"
    kubectl get pods -n argocd
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ArgoCD Applications 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "2️⃣ ArgoCD Applications 상태"

APP_COUNT=$(kubectl get applications -n argocd --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [ "$APP_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  ArgoCD Application이 없습니다${NC}"
    echo "   Root App을 배포하세요:"
    echo "   kubectl apply -f argocd/root-app.yaml"
    exit 0
fi

echo "총 Applications: $APP_COUNT"
echo ""

# 상태별로 분류
SYNCED=0
OUT_OF_SYNC=0
HEALTHY=0
PROGRESSING=0
DEGRADED=0
MISSING=0

while IFS= read -r line; do
    NAME=$(echo "$line" | awk '{print $1}')
    SYNC=$(echo "$line" | awk '{print $2}')
    HEALTH=$(echo "$line" | awk '{print $3}')
    
    # Sync Status
    if [ "$SYNC" = "Synced" ]; then
        SYNC_ICON="${GREEN}✅${NC}"
        SYNCED=$((SYNCED + 1))
    else
        SYNC_ICON="${RED}❌${NC}"
        OUT_OF_SYNC=$((OUT_OF_SYNC + 1))
    fi
    
    # Health Status
    case "$HEALTH" in
        "Healthy")
            HEALTH_ICON="${GREEN}🟢${NC}"
            HEALTHY=$((HEALTHY + 1))
            ;;
        "Progressing")
            HEALTH_ICON="${YELLOW}🟡${NC}"
            PROGRESSING=$((PROGRESSING + 1))
            ;;
        "Degraded")
            HEALTH_ICON="${RED}🔴${NC}"
            DEGRADED=$((DEGRADED + 1))
            ;;
        "Missing")
            HEALTH_ICON="${RED}⚫${NC}"
            MISSING=$((MISSING + 1))
            ;;
        *)
            HEALTH_ICON="⚪"
            ;;
    esac
    
    echo -e "  $SYNC_ICON $HEALTH_ICON $NAME"
    echo "       Sync: $SYNC | Health: $HEALTH"
    echo ""
done < <(kubectl get applications -n argocd --no-headers 2>/dev/null | awk '{print $1" "$2" "$3}')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 통계 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "3️⃣ 통계 요약"

echo "Sync Status:"
echo -e "  ${GREEN}✅ Synced:${NC} $SYNCED"
echo -e "  ${RED}❌ OutOfSync:${NC} $OUT_OF_SYNC"
echo ""

echo "Health Status:"
echo -e "  ${GREEN}🟢 Healthy:${NC} $HEALTHY"
echo -e "  ${YELLOW}🟡 Progressing:${NC} $PROGRESSING"
echo -e "  ${RED}🔴 Degraded:${NC} $DEGRADED"
echo -e "  ${RED}⚫ Missing:${NC} $MISSING"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 전체 상태 판정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "4️⃣ 전체 상태"

if [ "$SYNCED" -eq "$APP_COUNT" ] && [ "$HEALTHY" -eq "$APP_COUNT" ]; then
    echo -e "${GREEN}✅ 모든 Application이 정상입니다!${NC}"
    echo ""
    echo "🎉 GitOps 배포가 성공적으로 완료되었습니다."
    exit 0
elif [ "$PROGRESSING" -gt 0 ]; then
    echo -e "${YELLOW}⏳ 배포가 진행 중입니다...${NC}"
    echo ""
    echo "다음 명령어로 실시간 모니터링:"
    echo "  watch -n 5 './scripts/utilities/argocd-quick-status.sh'"
    exit 0
elif [ "$DEGRADED" -gt 0 ] || [ "$MISSING" -gt 0 ]; then
    echo -e "${RED}❌ 일부 Application에 문제가 있습니다${NC}"
    echo ""
    echo "트러블슈팅:"
    echo "  1. ArgoCD 대시보드 접속:"
    echo "     kubectl port-forward svc/argocd-server -n argocd 8080:443"
    echo "     https://localhost:8080"
    echo ""
    echo "  2. 문제가 있는 Application 확인:"
    kubectl get applications -n argocd --no-headers 2>/dev/null | grep -E "Degraded|Missing" | awk '{print $1}' | while read app; do
        echo "     kubectl describe application $app -n argocd"
    done
    exit 1
elif [ "$OUT_OF_SYNC" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Git과 클러스터가 동기화되지 않았습니다${NC}"
    echo ""
    echo "수동 Sync 필요:"
    kubectl get applications -n argocd --no-headers 2>/dev/null | grep -v "Synced" | awk '{print $1}' | while read app; do
        echo "  kubectl patch application $app -n argocd -p '{\"metadata\":{\"annotations\":{\"argocd.argoproj.io/refresh\":\"hard\"}}}' --type merge"
    done
    exit 1
else
    echo -e "${CYAN}ℹ️  상태 확인 중...${NC}"
    exit 0
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 빠른 접속 정보
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print_header "5️⃣ ArgoCD 접속 정보"

echo "🌐 ArgoCD 대시보드:"
echo "   kubectl port-forward svc/argocd-server -n argocd 8080:443"
echo "   https://localhost:8080"
echo ""

echo "🔑 로그인 정보:"
echo "   Username: admin"
echo "   Password:"
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d
echo ""
echo ""

echo "📚 더 자세한 가이드:"
echo "   docs/deployment/ARGOCD_MONITORING_GUIDE.md"
echo ""

