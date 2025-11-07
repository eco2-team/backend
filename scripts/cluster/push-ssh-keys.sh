#!/bin/bash
# EC2 Instance Connect SSH 키 푸시 스크립트
# EC2 Instance Connect 키는 60초 동안만 유효하므로 주기적으로 재푸시 필요

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 EC2 Instance Connect SSH 키 푸시"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# SSH 키 생성 (존재하지 않는 경우)
if [ ! -f ~/.ssh/k8s-temp ]; then
    echo "🔑 SSH 키 생성 중..."
    ssh-keygen -t rsa -f ~/.ssh/k8s-temp -N "" -q
    echo "✅ SSH 키 생성 완료"
else
    echo "✅ SSH 키가 이미 존재합니다"
fi
echo ""

# 모든 인스턴스 ID 가져오기
echo "🔍 인스턴스 ID 조회 중..."
INSTANCE_IDS=$(aws ec2 describe-instances \
    --region ap-northeast-2 \
    --filters "Name=tag:Name,Values=k8s-*" \
              "Name=instance-state-name,Values=running" \
    --query 'Reservations[*].Instances[*].[InstanceId,Placement.AvailabilityZone]' \
    --output text)

if [ -z "$INSTANCE_IDS" ]; then
    echo "❌ 실행 중인 인스턴스를 찾을 수 없습니다!"
    exit 1
fi

# 인스턴스 개수 계산
INSTANCE_COUNT=$(echo "$INSTANCE_IDS" | wc -l | tr -d ' ')
echo "✅ $INSTANCE_COUNT개 인스턴스 발견"
echo ""

# 모든 노드에 SSH 키 푸시
echo "🔑 모든 노드에 SSH 키 푸시 중..."
PUSH_COUNT=0
FAIL_COUNT=0

while read -r instance_id az; do
    if aws ec2-instance-connect send-ssh-public-key \
        --instance-id "$instance_id" \
        --availability-zone "$az" \
        --instance-os-user ubuntu \
        --ssh-public-key file://~/.ssh/k8s-temp.pub \
        --region ap-northeast-2 >/dev/null 2>&1; then
        echo "   ✅ $instance_id ($az)"
        PUSH_COUNT=$((PUSH_COUNT + 1))
    else
        echo "   ❌ $instance_id ($az) - 실패"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
done <<< "$INSTANCE_IDS"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 결과"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  총 인스턴스: $INSTANCE_COUNT"
echo "  성공: $PUSH_COUNT"
echo "  실패: $FAIL_COUNT"
echo ""

if [ $PUSH_COUNT -eq 0 ]; then
    echo "❌ 모든 키 푸시 실패!"
    exit 1
elif [ $FAIL_COUNT -gt 0 ]; then
    echo "⚠️  일부 키 푸시 실패 (성공: $PUSH_COUNT/$INSTANCE_COUNT)"
else
    echo "✅ 모든 노드에 SSH 키 푸시 완료!"
fi

echo ""
echo "⚠️  주의: EC2 Instance Connect 키는 60초 후 만료됩니다!"
echo "   즉시 SSH 또는 Ansible을 실행하세요."
echo ""

