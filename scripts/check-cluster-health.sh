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
NC='\033[0m' # No Color

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

# 메모리 체크
MEM_AVAILABLE=$(free -m | awk 'NR==2 {print $7}')
if [ "$MEM_AVAILABLE" -gt 2000 ]; then
  check_pass "메모리 여유: ${MEM_AVAILABLE}MB"
elif [ "$MEM_AVAILABLE" -gt 1000 ]; then
  check_warn "메모리 부족 가능성: ${MEM_AVAILABLE}MB"
else
  check_fail "메모리 부족: ${MEM_AVAILABLE}MB"
fi

# Swap 체크
if [ "$(swapon -s)" == "" ]; then
  check_pass "Swap 비활성화"
else
  check_fail "Swap 활성화됨"
fi

# 디스크 체크
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

# containerd 실행
if systemctl is-active containerd >/dev/null 2>&1; then
  check_pass "containerd 실행 중"
else
  check_fail "containerd 중지됨"
fi

# pause image 확인
PAUSE_IMAGE=$(grep "sandbox_image" /etc/containerd/config.toml | grep -o 'registry.k8s.io/pause:[0-9.]*' | head -1)
if [ "$PAUSE_IMAGE" == "registry.k8s.io/pause:3.9" ]; then
  check_pass "pause image: $PAUSE_IMAGE"
else
  check_fail "pause image 불일치: $PAUSE_IMAGE (expected 3.9)"
fi

# SystemdCgroup 확인
if grep -q "SystemdCgroup = true" /etc/containerd/config.toml; then
  check_pass "SystemdCgroup 활성화"
else
  check_fail "SystemdCgroup 비활성화"
fi

# CRI 소켓
if [ -S /run/containerd/containerd.sock ]; then
  check_pass "CRI 소켓 존재"
else
  check_fail "CRI 소켓 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  Control Plane 컴포넌트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# crictl로 컨테이너 상태 확인
for component in etcd kube-apiserver kube-controller-manager kube-scheduler; do
  STATE=$(sudo crictl ps -a | grep "$component" | head -1 | awk '{print $4}')
  if [ "$STATE" == "Running" ]; then
    check_pass "$component: Running"
  elif [ "$STATE" == "Exited" ]; then
    check_fail "$component: Exited (죽어있음!)"
  else
    check_warn "$component: $STATE"
  fi
done

# API 서버 응답 확인
if kubectl get --raw /healthz >/dev/null 2>&1; then
  check_pass "API 서버 응답 정상"
else
  check_fail "API 서버 응답 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  노드 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v kubectl >/dev/null 2>&1 && kubectl get nodes >/dev/null 2>&1; then
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
echo "5️⃣  Pod 재시작 횟수"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get pods -A >/dev/null 2>&1; then
  echo "재시작 많은 Pod (상위 5개):"
  kubectl get pods -A --sort-by='.status.containerStatuses[0].restartCount' 2>/dev/null | grep -v "RESTARTS" | tail -5 | while read line; do
    RESTARTS=$(echo "$line" | awk '{print $5}')
    NAME=$(echo "$line" | awk '{print $2}')
    if [ "$RESTARTS" -gt 5 ]; then
      echo -e "  ${RED}❌${NC} $NAME: $RESTARTS 재시작"
    elif [ "$RESTARTS" -gt 2 ]; then
      echo -e "  ${YELLOW}⚠️${NC} $NAME: $RESTARTS 재시작"
    else
      echo -e "  ${GREEN}✅${NC} $NAME: $RESTARTS 재시작"
    fi
  done
else
  echo "  API 서버 접근 불가"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  네트워크 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# sysctl 확인
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

# CNI 설정
if [ -d /etc/cni/net.d ] && [ "$(ls -A /etc/cni/net.d 2>/dev/null)" ]; then
  check_pass "CNI 설정 파일 존재"
  echo "  파일: $(ls /etc/cni/net.d/)"
elif [ -d /etc/cni/net.d ]; then
  check_warn "CNI 디렉토리 비어있음"
else
  check_fail "CNI 디렉토리 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣  kube-proxy 설정"
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

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣  Calico CNI"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
echo "9️⃣  CrashLoopBackOff Pod 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get pods -A >/dev/null 2>&1; then
  CRASH_PODS=$(kubectl get pods -A 2>/dev/null | grep -c "CrashLoopBackOff" || echo "0")
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
  echo "  API 서버 접근 불가"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔟 Kubernetes 버전 일치성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBEADM_VER=$(kubeadm version -o short 2>/dev/null)
KUBELET_VER=$(kubelet --version 2>/dev/null | awk '{print $2}')
KUBECTL_VER=$(kubectl version --client -o json 2>/dev/null | grep -o 'v[0-9.]*' | head -1)

echo "  kubeadm: $KUBEADM_VER"
echo "  kubelet: $KUBELET_VER"
echo "  kubectl: $KUBECTL_VER"

if [ "$KUBEADM_VER" == "$KUBELET_VER" ]; then
  check_pass "kubeadm-kubelet 버전 일치"
else
  check_fail "버전 불일치: kubeadm=$KUBEADM_VER, kubelet=$KUBELET_VER"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣1️⃣  API 서버 안정성 테스트 (30초)"
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
done

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
echo "1️⃣2️⃣  최근 에러 로그 (kubelet)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

KUBELET_ERRORS=$(sudo journalctl -u kubelet --since "5 minutes ago" --no-pager 2>/dev/null | grep -c "Error\|FATAL" || echo "0")
if [ "$KUBELET_ERRORS" -lt 10 ]; then
  check_pass "kubelet 에러: $KUBELET_ERRORS개 (5분 이내)"
elif [ "$KUBELET_ERRORS" -lt 50 ]; then
  check_warn "kubelet 에러 다수: $KUBELET_ERRORS개"
else
  check_fail "kubelet 에러 과다: $KUBELET_ERRORS개"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣3️⃣  etcd 데이터 무결성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d /var/lib/etcd/member ]; then
  ETCD_SIZE=$(du -sh /var/lib/etcd 2>/dev/null | awk '{print $1}')
  echo "  etcd 데이터 크기: $ETCD_SIZE"
  check_pass "etcd 데이터 존재"
else
  check_warn "etcd 데이터 디렉토리 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣4️⃣  CoreDNS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if kubectl get deployment coredns -n kube-system >/dev/null 2>&1; then
  DESIRED=$(kubectl get deployment coredns -n kube-system -o jsonpath='{.spec.replicas}' 2>/dev/null)
  READY=$(kubectl get deployment coredns -n kube-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
  
  if [ "$DESIRED" -eq "$READY" ]; then
    check_pass "CoreDNS: $READY/$DESIRED Ready"
  else
    check_warn "CoreDNS: $READY/$DESIRED Ready"
  fi
else
  echo "  CoreDNS 확인 불가"
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
  echo "  → Ansible 계속 진행 가능"
elif [ "$PERCENTAGE" -ge 70 ]; then
  echo -e "${YELLOW}⚠️  클러스터 불안정${NC}"
  echo "  → 일부 문제 해결 필요"
else
  echo -e "${RED}❌ 클러스터 심각한 불안정${NC}"
  echo "  → 재구축 권장"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 권장 조치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$PERCENTAGE" -lt 70 ]; then
  echo "  1. 전체 재구축:"
  echo "     ./scripts/rebuild-cluster.sh"
  echo ""
  echo "  2. containerd 재시작:"
  echo "     sudo systemctl restart containerd"
  echo "     sudo systemctl restart kubelet"
elif [ "$PERCENTAGE" -lt 90 ]; then
  echo "  1. 문제 Pod 재시작:"
  echo "     kubectl delete pods -A --field-selector status.phase=Failed"
  echo ""
  echo "  2. API 서버 대기 후 재시도"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


