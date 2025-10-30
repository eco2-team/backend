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

# 스왑 비활성화 (Kubernetes 요구사항)
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# 타임존 설정
timedatectl set-timezone Asia/Seoul

echo "✅ 기본 설정 완료: ${hostname}"

