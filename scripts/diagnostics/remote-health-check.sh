#!/bin/bash
# 원격으로 클러스터 헬스체크를 실행하는 스크립트

NODE_NAME=${1:-master}
REGION=${AWS_REGION:-ap-northeast-2}
SSH_KEY=${SSH_KEY:-~/.ssh/sesacthon}

# 사용법
if [ "$NODE_NAME" == "-h" ] || [ "$NODE_NAME" == "--help" ]; then
  echo "사용법: $0 [node-name]"
  echo ""
  echo "예시:"
  echo "  $0 master     # Master 노드 헬스체크 (기본값)"
  echo "  $0 worker-1   # Worker 1 헬스체크"
  echo "  $0 worker-2   # Worker 2 헬스체크"
  exit 0
fi

echo "🔍 $NODE_NAME 노드 Public IP 검색 중..."

# Public IP 조회
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-$NODE_NAME" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].PublicIpAddress" \
  --output text \
  --region $REGION)

if [ -z "$PUBLIC_IP" ]; then
  echo "❌ $NODE_NAME 인스턴스를 찾을 수 없습니다."
  exit 1
fi

echo "✅ $NODE_NAME Public IP: $PUBLIC_IP"
echo "🔄 원격 헬스체크 시작..."
echo ""

# SSH로 헬스체크 스크립트 전송 및 실행
ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$PUBLIC_IP 'bash -s' <<'ENDSSH'
#!/bin/bash
# Kubernetes 클러스터 안정성 점검 스크립트
# Master 노드에서 실행

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Kubernetes 클러스터 안정성 점검"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

score=0
max_score=0

check_pass() {
  echo -e "${GREEN}✅ PASS${NC}: $1"
  score=$((score + 1))
  max_score=$((max_score + 1))
}

check_fail() {
  echo -e "${RED}❌ FAIL${NC}: $1"
  max_score=$((max_score + 1))
}

check_warn() {
  echo -e "${YELLOW}⚠️  WARN${NC}: $1"
  max_score=$((max_score + 1))
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  시스템 리소스"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

MEM_AVAILABLE=$(free -m | awk 'NR==2 {print $7}')
if [ "$MEM_AVAILABLE" -gt 2000 ]; then
  check_pass "메모리 여유: ${MEM_AVAILABLE}MB"
elif [ "$MEM_AVAILABLE" -gt 1000 ]; then
  check_warn "메모리 부족 가능성: ${MEM_AVAILABLE}MB"
else
  check_fail "메모리 부족: ${MEM_AVAILABLE}MB"
fi

if [ "$(swapon -s)" == "" ]; then
  check_pass "Swap 비활성화"
else
  check_fail "Swap 활성화됨"
fi

DISK_USAGE=$(df -h /var/lib/etcd 2>/dev/null | awk 'NR==2 {print $5}' | sed 's/%//')
if [ -z "$DISK_USAGE" ]; then
  DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
fi
if [ "$DISK_USAGE" -lt 80 ]; then
  check_pass "디스크 사용량: ${DISK_USAGE}%"
else
  check_warn "디스크 사용량 높음: ${DISK_USAGE}%"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  containerd 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if systemctl is-active containerd >/dev/null 2>&1; then
  check_pass "containerd 실행 중"
else
  check_fail "containerd 중지됨"
fi

PAUSE_IMAGE=$(grep "sandbox_image" /etc/containerd/config.toml | grep -o 'registry.k8s.io/pause:[0-9.]*' | head -1)
if [ "$PAUSE_IMAGE" == "registry.k8s.io/pause:3.9" ]; then
  check_pass "pause image: $PAUSE_IMAGE"
else
  check_fail "pause image 불일치: $PAUSE_IMAGE (expected 3.9)"
fi

if grep -q "SystemdCgroup = true" /etc/containerd/config.toml; then
  check_pass "SystemdCgroup 활성화"
else
  check_fail "SystemdCgroup 비활성화"
fi

if [ -S /run/containerd/containerd.sock ]; then
  check_pass "CRI 소켓 존재"
else
  check_fail "CRI 소켓 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  Control Plane 컴포넌트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for component in etcd kube-apiserver kube-controller-manager kube-scheduler; do
  STATE=$(sudo crictl ps -a 2>/dev/null | grep "$component" | head -1 | awk '{print $4}')
  if [ "$STATE" == "Running" ]; then
    check_pass "$component: Running"
  elif [ "$STATE" == "Exited" ]; then
    check_fail "$component: Exited (죽어있음!)"
  elif [ -z "$STATE" ]; then
    check_fail "$component: 컨테이너 없음"
  else
    check_warn "$component: $STATE"
  fi
done

if kubectl get --raw /healthz >/dev/null 2>&1; then
  check_pass "API 서버 응답 정상"
else
  check_fail "API 서버 응답 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  노드 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get nodes >/dev/null 2>&1; then
  TOTAL_NODES=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
  READY_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -w "Ready" | wc -l | tr -d ' ')
  
  if [ "$TOTAL_NODES" -eq 3 ] && [ "$READY_NODES" -eq 3 ]; then
    check_pass "노드: $READY_NODES/$TOTAL_NODES Ready"
  elif [ "$READY_NODES" -gt 0 ]; then
    check_warn "노드: $READY_NODES/$TOTAL_NODES Ready"
  else
    check_fail "노드: $READY_NODES/$TOTAL_NODES Ready"
  fi
else
  check_fail "kubectl 사용 불가 (API 서버 문제)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  CrashLoopBackOff Pod 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get pods -A >/dev/null 2>&1; then
  CRASH_PODS=$(kubectl get pods -A 2>/dev/null | grep "CrashLoopBackOff" | wc -l | tr -d ' ')
  if [ -z "$CRASH_PODS" ]; then
    CRASH_PODS=0
  fi
  
  if [ "$CRASH_PODS" -eq 0 ]; then
    check_pass "CrashLoopBackOff Pod: 없음"
  else
    check_fail "CrashLoopBackOff Pod: ${CRASH_PODS}개"
    echo ""
    echo "  CrashLoopBackOff Pod 목록:"
    kubectl get pods -A 2>/dev/null | grep "CrashLoopBackOff" | while read line; do
      echo -e "    ${RED}→${NC} $line"
    done
  fi
else
  check_fail "API 서버 접근 불가"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  API 서버 안정성 테스트 (30초)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SUCCESS=0
FAIL=0
for i in {1..30}; do
  if kubectl get --raw /healthz >/dev/null 2>&1; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
  sleep 1
  echo -ne "\r  테스트 진행: $i/30 (성공: $SUCCESS, 실패: $FAIL)"
done
echo ""

SUCCESS_RATE=$((SUCCESS * 100 / 30))
echo "  성공: $SUCCESS/30 (${SUCCESS_RATE}%)"
echo "  실패: $FAIL/30"

if [ "$SUCCESS_RATE" -ge 90 ]; then
  check_pass "API 서버 안정성: ${SUCCESS_RATE}%"
elif [ "$SUCCESS_RATE" -ge 70 ]; then
  check_warn "API 서버 불안정: ${SUCCESS_RATE}%"
else
  check_fail "API 서버 심각한 불안정: ${SUCCESS_RATE}%"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣  네트워크 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$(sysctl -n net.ipv4.ip_forward)" == "1" ]; then
  check_pass "IP forward 활성화"
else
  check_fail "IP forward 비활성화"
fi

if [ "$(sysctl -n net.bridge.bridge-nf-call-iptables)" == "1" ]; then
  check_pass "bridge-nf-call-iptables 활성화"
else
  check_fail "bridge-nf-call-iptables 비활성화"
fi

if [ -d /etc/cni/net.d ] && [ "$(ls -A /etc/cni/net.d 2>/dev/null)" ]; then
  check_pass "CNI 설정 파일 존재"
else
  check_warn "CNI 설정 파일 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣  kube-proxy & Calico"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get daemonset kube-proxy -n kube-system >/dev/null 2>&1; then
  DESIRED=$(kubectl get daemonset kube-proxy -n kube-system -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null)
  READY=$(kubectl get daemonset kube-proxy -n kube-system -o jsonpath='{.status.numberReady}' 2>/dev/null)
  
  if [ "$DESIRED" -eq "$READY" ] && [ "$READY" -gt 0 ]; then
    check_pass "kube-proxy: $READY/$DESIRED Ready"
  else
    check_warn "kube-proxy: $READY/$DESIRED Ready"
  fi
else
  check_fail "kube-proxy DaemonSet 없음"
fi

if kubectl get daemonset calico-node -n kube-system >/dev/null 2>&1; then
  DESIRED=$(kubectl get daemonset calico-node -n kube-system -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null)
  READY=$(kubectl get daemonset calico-node -n kube-system -o jsonpath='{.status.numberReady}' 2>/dev/null)
  
  if [ "$DESIRED" -eq "$READY" ] && [ "$READY" -gt 0 ]; then
    check_pass "Calico: $READY/$DESIRED Ready"
  else
    check_warn "Calico: $READY/$DESIRED Ready"
  fi
else
  check_fail "Calico DaemonSet 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 최종 점수"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PERCENTAGE=$((score * 100 / max_score))
echo ""
echo "  점수: $score / $max_score ($PERCENTAGE%)"
echo ""

if [ "$PERCENTAGE" -ge 90 ]; then
  echo -e "${GREEN}✅ 클러스터 안정적${NC}"
  echo "  → 계속 진행 가능"
  exit 0
elif [ "$PERCENTAGE" -ge 70 ]; then
  echo -e "${YELLOW}⚠️  클러스터 불안정${NC}"
  echo "  → 일부 문제 해결 필요"
  exit 1
else
  echo -e "${RED}❌ 클러스터 심각한 불안정${NC}"
  echo "  → 재구축 권장"
  exit 2
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ENDSSH

EXIT_CODE=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $EXIT_CODE -eq 0 ]; then
  echo "✅ 헬스체크 성공! 클러스터 안정적입니다."
elif [ $EXIT_CODE -eq 1 ]; then
  echo "⚠️  헬스체크 경고! 클러스터가 불안정합니다."
elif [ $EXIT_CODE -eq 2 ]; then
  echo "❌ 헬스체크 실패! 클러스터 재구축을 권장합니다."
else
  echo "❌ SSH 연결 또는 스크립트 실행 실패"
fi

exit $EXIT_CODE

