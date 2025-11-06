#!/bin/bash
# 원격으로 Kubernetes 노드를 완전 초기화하는 스크립트

NODE_NAME=${1}
REGION=${AWS_REGION:-ap-northeast-2}
SSH_KEY=${SSH_KEY:-~/.ssh/sesacthon}

# 사용법 확인
if [ -z "$NODE_NAME" ]; then
  echo "❌ 노드 이름을 지정하세요."
  echo ""
  echo "사용법: $0 <node-name>"
  echo ""
  echo "예시:"
  echo "  $0 master     # Master 노드 초기화"
  echo "  $0 worker-1   # Worker 1 초기화"
  echo "  $0 worker-2   # Worker 2 초기화"
  echo "  $0 storage    # Storage 노드 초기화"
  echo "  $0 all        # 모든 노드 초기화"
  exit 1
fi

# 모든 노드 초기화
if [ "$NODE_NAME" == "all" ]; then
  echo "🔄 모든 노드 초기화 시작..."
  echo ""
  $0 master
  $0 worker-1
  $0 worker-2
  $0 storage
  echo ""
  echo "✅ 모든 노드 초기화 완료!"
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
echo "🔄 원격 초기화 시작..."
echo ""

# SSH로 원격 초기화 스크립트 실행
ssh -i $SSH_KEY -o StrictHostKeyChecking=no ubuntu@$PUBLIC_IP 'bash -s' << 'ENDSSH'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 Kubernetes 클러스터 완전 초기화"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. kubeadm reset
echo "1️⃣ kubeadm reset 실행..."
sudo kubeadm reset -f 2>/dev/null || echo "   (kubeadm reset 건너뜀)"
echo "✅ kubeadm reset 완료"
echo ""

# 2. Kubernetes 설정 파일 삭제
echo "2️⃣ Kubernetes 설정 파일 삭제..."
sudo rm -rf /etc/kubernetes/
sudo rm -rf /var/lib/etcd/
sudo rm -rf /var/lib/kubelet/
sudo rm -rf /etc/cni/net.d/
sudo rm -rf ~/.kube/
sudo rm -rf /var/lib/cni/
sudo rm -rf /opt/cni/bin/
echo "✅ 설정 파일 삭제 완료"
echo ""

# 3. 네트워크 인터페이스 삭제
echo "3️⃣ 네트워크 인터페이스 정리..."
sudo ip link delete cni0 2>/dev/null || true
sudo ip link delete flannel.1 2>/dev/null || true
sudo ip link delete tunl0 2>/dev/null || true
sudo ip link delete vxlan.calico 2>/dev/null || true
sudo ip link delete docker0 2>/dev/null || true
echo "✅ 네트워크 인터페이스 정리 완료"
echo ""

# 4. iptables 규칙 초기화
echo "4️⃣ iptables 규칙 초기화..."
sudo iptables -F 2>/dev/null || true
sudo iptables -t nat -F 2>/dev/null || true
sudo iptables -t mangle -F 2>/dev/null || true
sudo iptables -X 2>/dev/null || true
sudo iptables -t nat -X 2>/dev/null || true
sudo iptables -t mangle -X 2>/dev/null || true
echo "✅ iptables 규칙 초기화 완료"
echo ""

# 5. 컨테이너 정리
echo "5️⃣ 남은 컨테이너 정리..."
sudo crictl rm $(sudo crictl ps -a -q) 2>/dev/null || true
sudo crictl rmi $(sudo crictl images -q) 2>/dev/null || true
echo "✅ 컨테이너 정리 완료"
echo ""

# 6. containerd 재시작
echo "6️⃣ containerd 재시작..."
sudo systemctl restart containerd
sudo systemctl restart kubelet 2>/dev/null || true
sleep 2
echo "✅ containerd 재시작 완료"
echo ""

# 7. 최종 확인
echo "7️⃣ 최종 확인..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Swap 상태:"
if [ -z "$(swapon -s)" ]; then
  echo "  ✅ Swap OFF"
else
  echo "  ⚠️ Swap ON"
fi
echo ""

echo "CNI 네트워크 인터페이스:"
CNI_INTERFACES=$(ip link show | grep -E "cni|flannel|calico|tunl|vxlan" || echo "")
if [ -z "$CNI_INTERFACES" ]; then
  echo "  ✅ CNI 인터페이스 없음"
else
  echo "  ⚠️ 일부 인터페이스 남아있음:"
  echo "$CNI_INTERFACES"
fi
echo ""

echo "Containerd 상태:"
CONTAINERD_STATUS=$(sudo systemctl is-active containerd)
if [ "$CONTAINERD_STATUS" == "active" ]; then
  echo "  ✅ $CONTAINERD_STATUS"
else
  echo "  ⚠️ $CONTAINERD_STATUS"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 클러스터 완전 초기화 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ENDSSH

SSH_EXIT_CODE=$?

echo ""
if [ $SSH_EXIT_CODE -eq 0 ]; then
  echo "✅ $NODE_NAME 노드 초기화 성공!"
else
  echo "❌ $NODE_NAME 노드 초기화 실패 (Exit code: $SSH_EXIT_CODE)"
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


