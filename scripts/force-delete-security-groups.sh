#!/bin/bash
# Security Group 강제 삭제 스크립트
# 순환 참조를 해결하고 Security Group을 삭제합니다

set -e

REGION=${AWS_REGION:-ap-northeast-2}
MASTER_SG_ID="sg-0afdc5528d5cf7d1c"
WORKER_SG_ID="sg-06d0aec7f41806b51"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗑️  Security Group 강제 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Security Group이 존재하는지 확인
check_sg_exists() {
  local SG_ID=$1
  aws ec2 describe-security-groups \
    --region ${REGION} \
    --group-ids ${SG_ID} \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "not-found"
}

# Security Group 규칙 제거 함수
revoke_all_rules() {
  local SG_ID=$1
  local SG_NAME=$2

  echo "🔧 ${SG_NAME} (${SG_ID}) 규칙 제거 중..."

  # Ingress 규칙 가져오기
  INGRESS_RULES=$(aws ec2 describe-security-groups \
    --region ${REGION} \
    --group-ids ${SG_ID} \
    --query 'SecurityGroups[0].IpPermissions' \
    --output json 2>/dev/null)

  if [ "$INGRESS_RULES" != "[]" ] && [ "$INGRESS_RULES" != "null" ]; then
    echo "  📥 Ingress 규칙 제거 중..."
    aws ec2 revoke-security-group-ingress \
      --region ${REGION} \
      --group-id ${SG_ID} \
      --ip-permissions "${INGRESS_RULES}" 2>/dev/null && echo "  ✅ Ingress 규칙 제거 완료" || echo "  ⚠️  일부 규칙 제거 실패 (무시)"
  else
    echo "  ✅ Ingress 규칙 없음"
  fi

  # Egress 규칙 가져오기
  EGRESS_RULES=$(aws ec2 describe-security-groups \
    --region ${REGION} \
    --group-ids ${SG_ID} \
    --query 'SecurityGroups[0].IpPermissionsEgress' \
    --output json 2>/dev/null)

  if [ "$EGRESS_RULES" != "[]" ] && [ "$EGRESS_RULES" != "null" ]; then
    echo "  📤 Egress 규칙 제거 중..."
    aws ec2 revoke-security-group-egress \
      --region ${REGION} \
      --group-id ${SG_ID} \
      --ip-permissions "${EGRESS_RULES}" 2>/dev/null && echo "  ✅ Egress 규칙 제거 완료" || echo "  ⚠️  일부 규칙 제거 실패 (무시)"
  else
    echo "  ✅ Egress 규칙 없음"
  fi

  echo ""
}

# Security Group 삭제 함수
delete_sg() {
  local SG_ID=$1
  local SG_NAME=$2

  echo "🗑️  ${SG_NAME} (${SG_ID}) 삭제 중..."

  if aws ec2 delete-security-group \
    --region ${REGION} \
    --group-id ${SG_ID} 2>/dev/null; then
    echo "  ✅ 삭제 완료"
  else
    echo "  ❌ 삭제 실패"
    return 1
  fi
  echo ""
}

# 1단계: Master SG 규칙 제거
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  단계 1: Security Group 규칙 제거"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

MASTER_EXISTS=$(check_sg_exists ${MASTER_SG_ID})
WORKER_EXISTS=$(check_sg_exists ${WORKER_SG_ID})

if [ "$MASTER_EXISTS" != "not-found" ]; then
  revoke_all_rules ${MASTER_SG_ID} "Master SG"
else
  echo "✅ Master SG가 이미 삭제됨"
  echo ""
fi

if [ "$WORKER_EXISTS" != "not-found" ]; then
  revoke_all_rules ${WORKER_SG_ID} "Worker SG"
else
  echo "✅ Worker SG가 이미 삭제됨"
  echo ""
fi

# 약간의 대기 시간
echo "⏳ AWS 전파 대기 중 (5초)..."
sleep 5
echo ""

# 2단계: Security Group 삭제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  단계 2: Security Group 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FAILED=0

if [ "$MASTER_EXISTS" != "not-found" ]; then
  delete_sg ${MASTER_SG_ID} "Master SG" || FAILED=1
fi

if [ "$WORKER_EXISTS" != "not-found" ]; then
  delete_sg ${WORKER_SG_ID} "Worker SG" || FAILED=1
fi

# 결과 요약
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 결과 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

MASTER_FINAL=$(check_sg_exists ${MASTER_SG_ID})
WORKER_FINAL=$(check_sg_exists ${WORKER_SG_ID})

if [ "$MASTER_FINAL" == "not-found" ]; then
  echo "✅ Master SG: 삭제됨"
else
  echo "❌ Master SG: 아직 존재함 (${MASTER_SG_ID})"
fi

if [ "$WORKER_FINAL" == "not-found" ]; then
  echo "✅ Worker SG: 삭제됨"
else
  echo "❌ Worker SG: 아직 존재함 (${WORKER_SG_ID})"
fi

echo ""

if [ "$MASTER_FINAL" == "not-found" ] && [ "$WORKER_FINAL" == "not-found" ]; then
  echo "🎉 모든 Security Group이 성공적으로 삭제되었습니다!"
  echo "💡 이제 terraform destroy를 다시 실행할 수 있습니다."
  exit 0
else
  echo "⚠️  일부 Security Group이 아직 남아있습니다."
  echo "💡 잠시 후 다시 시도하거나, terraform destroy를 계속 실행하세요."
  exit 1
fi
