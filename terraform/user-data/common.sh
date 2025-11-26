#!/bin/bash
set -e

# 호스트명 설정
hostnamectl set-hostname ${hostname}

# /etc/hosts 업데이트
echo "127.0.0.1 ${hostname}" >> /etc/hosts

# 시스템 업데이트
apt-get update
apt-get upgrade -y

# 필수 패키지 설치
apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools

# SSM Agent 설치 (Session Manager용)
# Ubuntu 22.04는 기본 포함되어 있지만 명시적으로 설치
snap install amazon-ssm-agent --classic

# Region 설정 (Snap 환경)
# Snap은 /etc/amazon/ssm/ 접근 불가 → /var/snap 사용
mkdir -p /var/snap/amazon-ssm-agent/common
cat > /var/snap/amazon-ssm-agent/common/amazon-ssm-agent.json << 'JSON'
{
  "Region": "ap-northeast-2"
}
JSON

# SSM Agent 시작
systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent.service
systemctl start snap.amazon-ssm-agent.amazon-ssm-agent.service

# SSM Agent 상태 확인
systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service || true

# 등록 대기 (Region 설정 반영)
echo "⏳ SSM Agent 등록 대기 중... (10초)"
sleep 10

# 스왑 비활성화 (Kubernetes 요구사항)
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# 타임존 설정
timedatectl set-timezone Asia/Seoul

%{ if kubelet_extra_args != "" }
# Kubelet node labels/taints (pre-create drop-in so kubeadm join picks it up)
mkdir -p /etc/systemd/system/kubelet.service.d
cat <<EOF >/etc/systemd/system/kubelet.service.d/10-node-labels.conf
[Service]
Environment="KUBELET_EXTRA_ARGS=${kubelet_extra_args}"
EOF
systemctl daemon-reload || true
%{ endif }

echo "✅ 기본 설정 완료: ${hostname}"
echo "✅ SSM Agent 활성화됨"
