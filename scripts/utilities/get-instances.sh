#!/bin/bash
# 실제 인스턴스 ID 조회 스크립트

REGION=${AWS_REGION:-ap-northeast-2}

echo "🔍 K8s 클러스터 인스턴스 검색 중..."
echo ""

# Master
MASTER_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-master" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,PublicIpAddress,State.Name]" \
  --output text \
  --region $REGION)

if [ -n "$MASTER_ID" ]; then
  echo "✅ Master:"
  echo "   Instance ID: $(echo $MASTER_ID | awk '{print $1}')"
  echo "   Public IP: $(echo $MASTER_ID | awk '{print $2}')"
  echo "   State: $(echo $MASTER_ID | awk '{print $3}')"
else
  echo "❌ Master 인스턴스 없음"
fi

echo ""

# Worker 1
WORKER1_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-worker-1" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,PublicIpAddress,State.Name]" \
  --output text \
  --region $REGION)

if [ -n "$WORKER1_ID" ]; then
  echo "✅ Worker 1:"
  echo "   Instance ID: $(echo $WORKER1_ID | awk '{print $1}')"
  echo "   Public IP: $(echo $WORKER1_ID | awk '{print $2}')"
  echo "   State: $(echo $WORKER1_ID | awk '{print $3}')"
else
  echo "❌ Worker 1 인스턴스 없음"
fi

echo ""

# Worker 2
WORKER2_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-worker-2" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,PublicIpAddress,State.Name]" \
  --output text \
  --region $REGION)

if [ -n "$WORKER2_ID" ]; then
  echo "✅ Worker 2:"
  echo "   Instance ID: $(echo $WORKER2_ID | awk '{print $1}')"
  echo "   Public IP: $(echo $WORKER2_ID | awk '{print $2}')"
  echo "   State: $(echo $WORKER2_ID | awk '{print $3}')"
else
  echo "❌ Worker 2 인스턴스 없음"
fi

echo ""

# Storage
STORAGE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-storage" "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[InstanceId,PublicIpAddress,State.Name]" \
  --output text \
  --region $REGION)

if [ -n "$STORAGE_ID" ]; then
  echo "✅ Storage:"
  echo "   Instance ID: $(echo $STORAGE_ID | awk '{print $1}')"
  echo "   Public IP: $(echo $STORAGE_ID | awk '{print $2}')"
  echo "   State: $(echo $STORAGE_ID | awk '{print $3}')"
else
  echo "❌ Storage 인스턴스 없음"
fi

echo ""
echo "📝 Session Manager 접속 명령어:"
if [ -n "$MASTER_ID" ]; then
  echo "Master: aws ssm start-session --target $(echo $MASTER_ID | awk '{print $1}')"
fi
if [ -n "$WORKER1_ID" ]; then
  echo "Worker 1: aws ssm start-session --target $(echo $WORKER1_ID | awk '{print $1}')"
fi
if [ -n "$WORKER2_ID" ]; then
  echo "Worker 2: aws ssm start-session --target $(echo $WORKER2_ID | awk '{print $1}')"
fi
if [ -n "$STORAGE_ID" ]; then
  echo "Storage: aws ssm start-session --target $(echo $STORAGE_ID | awk '{print $1}')"
fi
