#!/bin/bash
# Kubernetes 클러스터 완전 초기화 스크립트

echo "🔄 Kubernetes 클러스터 완전 초기화 시작..."
echo ""

# 1. kubeadm reset
echo "1️⃣ kubeadm reset 실행..."
sudo kubeadm reset -f
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

# 3. 네트워크 인터페이스 삭제 (CNI 충돌 방지)
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
sudo iptables -F
sudo iptables -t nat -F
sudo iptables -t mangle -F
sudo iptables -X
sudo iptables -t nat -X
sudo iptables -t mangle -X
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
echo "✅ containerd 재시작 완료"
echo ""

# 7. 최종 확인
echo "7️⃣ 최종 확인..."
echo "Swap 상태:"
swapon -s || echo "Swap OFF ✅"
echo ""
echo "네트워크 인터페이스:"
ip link show | grep -E "cni|flannel|calico|tunl|vxlan" || echo "CNI 인터페이스 없음 ✅"
echo ""
echo "Containerd 상태:"
sudo systemctl is-active containerd
echo ""

echo "✅ 클러스터 완전 초기화 완료!"
echo ""
echo "📝 다음 단계:"
echo "   cd ansible"
echo "   ansible-playbook -i inventory/hosts.ini site.yml"


