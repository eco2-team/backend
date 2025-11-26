#!/bin/bash
# VPC 관련 리소스 강제 정리 스크립트
# Terraform destroy 전에 실행하여 VPC 삭제를 방해하는 리소스 제거

set -e

REGION=${AWS_REGION:-ap-northeast-2}
PROJECT_TAG="SeSACTHON"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 VPC 리소스 정리 스크립트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# VPC ID 찾기
echo "🔍 VPC 검색 중..."
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
  --region ${REGION} \
  --query 'Vpcs[0].VpcId' \
  --output text 2>/dev/null)

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
  echo "✅ VPC를 찾을 수 없습니다. 이미 정리되었거나 존재하지 않습니다."
  exit 0
fi

echo "📍 VPC ID: ${VPC_ID}"
echo ""

# 0. Target Groups 삭제 (Load Balancer 이전에)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "0️⃣  Target Groups 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

TG_ARNS=$(aws elbv2 describe-target-groups \
  --region ${REGION} \
  --query "TargetGroups[?VpcId=='${VPC_ID}'].TargetGroupArn" \
  --output text 2>/dev/null)

if [ -n "$TG_ARNS" ]; then
  echo "$TG_ARNS" | tr '\t' '\n' | while read TG_ARN; do
    if [ -n "$TG_ARN" ]; then
      TG_NAME=$(aws elbv2 describe-target-groups \
        --target-group-arns ${TG_ARN} \
        --region ${REGION} \
        --query 'TargetGroups[0].TargetGroupName' \
        --output text 2>/dev/null)
      echo "  🗑️  삭제 중: ${TG_NAME}"
      aws elbv2 delete-target-group \
        --target-group-arn ${TG_ARN} \
        --region ${REGION} 2>/dev/null || echo "  ⚠️  삭제 실패"
    fi
  done
else
  echo "  ✅ Target Group 없음"
fi
echo ""

# 1. Load Balancers 삭제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  Load Balancers 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

LB_ARNS=$(aws elbv2 describe-load-balancers \
  --region ${REGION} \
  --query "LoadBalancers[?VpcId=='${VPC_ID}'].LoadBalancerArn" \
  --output text 2>/dev/null)

if [ -n "$LB_ARNS" ]; then
  for LB_ARN in $LB_ARNS; do
    LB_NAME=$(aws elbv2 describe-load-balancers \
      --load-balancer-arns ${LB_ARN} \
      --region ${REGION} \
      --query 'LoadBalancers[0].LoadBalancerName' \
      --output text)
    echo "  🗑️  삭제 중: ${LB_NAME}"
    aws elbv2 delete-load-balancer \
      --load-balancer-arn ${LB_ARN} \
      --region ${REGION} 2>/dev/null || echo "  ⚠️  삭제 실패 (이미 삭제되었을 수 있음)"
  done
  echo "  ⏳ ALB 삭제 완료 대기 (30초)..."
  sleep 30
else
  echo "  ✅ Load Balancer 없음"
fi
echo ""

# 2. NAT Gateways 삭제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  NAT Gateways 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

NAT_IDS=$(aws ec2 describe-nat-gateways \
  --region ${REGION} \
  --filter "Name=vpc-id,Values=${VPC_ID}" "Name=state,Values=available" \
  --query 'NatGateways[*].NatGatewayId' \
  --output text 2>/dev/null)

if [ -n "$NAT_IDS" ]; then
  for NAT_ID in $NAT_IDS; do
    echo "  🗑️  삭제 중: ${NAT_ID}"
    aws ec2 delete-nat-gateway \
      --nat-gateway-id ${NAT_ID} \
      --region ${REGION} 2>/dev/null || echo "  ⚠️  삭제 실패"
  done
  echo "  ⏳ NAT Gateway 삭제 완료 대기 (60초)..."
  sleep 60
else
  echo "  ✅ NAT Gateway 없음"
fi
echo ""

# 3. VPC Endpoints 삭제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  VPC Endpoints 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

VPC_ENDPOINT_IDS=$(aws ec2 describe-vpc-endpoints \
  --region ${REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'VpcEndpoints[*].VpcEndpointId' \
  --output text 2>/dev/null)

if [ -n "$VPC_ENDPOINT_IDS" ]; then
  for VPC_ENDPOINT_ID in $VPC_ENDPOINT_IDS; do
    echo "  🗑️  삭제 중: ${VPC_ENDPOINT_ID}"
    aws ec2 delete-vpc-endpoints \
      --vpc-endpoint-ids ${VPC_ENDPOINT_ID} \
      --region ${REGION} 2>/dev/null || echo "  ⚠️  삭제 실패"
  done
else
  echo "  ✅ VPC Endpoint 없음"
fi
echo ""

# 4. Elastic IPs 해제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  Elastic IPs 해제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

EIP_ALLOCS=$(aws ec2 describe-addresses \
  --region ${REGION} \
  --filters "Name=domain,Values=vpc" \
  --query 'Addresses[?AssociationId==null].AllocationId' \
  --output text 2>/dev/null)

if [ -n "$EIP_ALLOCS" ]; then
  for ALLOC_ID in $EIP_ALLOCS; do
    echo "  🗑️  해제 중: ${ALLOC_ID}"
    aws ec2 release-address \
      --allocation-id ${ALLOC_ID} \
      --region ${REGION} 2>/dev/null || echo "  ⚠️  해제 실패"
  done
else
  echo "  ✅ 연결 해제된 Elastic IP 없음"
fi
echo ""

# 5. Security Groups 삭제
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣  Security Groups 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SG_IDS=$(aws ec2 describe-security-groups \
  --region ${REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query "SecurityGroups[?GroupName!='default'].GroupId" \
  --output text 2>/dev/null)

if [ -n "$SG_IDS" ]; then
  # 먼저 모든 Security Group 규칙 제거
  echo "  🔧 Security Group 규칙 제거 중..."
  for SG_ID in $SG_IDS; do
    # Egress 규칙 제거
    aws ec2 revoke-security-group-egress \
      --group-id $SG_ID \
      --ip-permissions '[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]' \
      --region ${REGION} 2>/dev/null || true

    # Ingress 규칙 제거
    aws ec2 revoke-security-group-ingress \
      --group-id $SG_ID \
      --source-group $SG_ID \
      --region ${REGION} 2>/dev/null || true
  done

  # Security Group 삭제
  echo "  🗑️  Security Groups 삭제 중..."
  for SG_ID in $SG_IDS; do
    SG_NAME=$(aws ec2 describe-security-groups \
      --group-ids $SG_ID \
      --region ${REGION} \
      --query 'SecurityGroups[0].GroupName' \
      --output text 2>/dev/null)
    echo "    삭제: ${SG_NAME} (${SG_ID})"
    aws ec2 delete-security-group \
      --group-id $SG_ID \
      --region ${REGION} 2>/dev/null || echo "    ⚠️  삭제 실패"
  done
else
  echo "  ✅ 삭제할 Security Group 없음"
fi
echo ""

# 6. Network Interfaces 확인 (정보만 출력)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣  Network Interfaces (ENI) 상태 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ENI_COUNT=$(aws ec2 describe-network-interfaces \
  --region ${REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'length(NetworkInterfaces)' \
  --output text 2>/dev/null)

if [ "$ENI_COUNT" -gt 0 ]; then
  echo "  ⚠️  남아있는 ENI: ${ENI_COUNT}개"
  echo "  💡 ENI는 ALB/NAT Gateway 삭제 후 자동으로 정리됩니다."
  echo "  ⏳ 추가 대기 중 (30초)..."
  sleep 30
else
  echo "  ✅ ENI 없음"
fi
echo ""

# 7. 최종 상태 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣  최종 상태 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REMAINING_LB=$(aws elbv2 describe-load-balancers --region ${REGION} --query "LoadBalancers[?VpcId=='${VPC_ID}'] | length(@)" --output text 2>/dev/null)
REMAINING_TG=$(aws elbv2 describe-target-groups --region ${REGION} --query "TargetGroups[?VpcId=='${VPC_ID}'] | length(@)" --output text 2>/dev/null)
REMAINING_SG=$(aws ec2 describe-security-groups --region ${REGION} --filters "Name=vpc-id,Values=${VPC_ID}" --query "SecurityGroups[?GroupName!='default'] | length(@)" --output text 2>/dev/null)
REMAINING_ENI=$(aws ec2 describe-network-interfaces --region ${REGION} --filters "Name=vpc-id,Values=${VPC_ID}" --query 'length(NetworkInterfaces)' --output text 2>/dev/null)
REMAINING_EIP=$(aws ec2 describe-addresses --region ${REGION} --filters "Name=domain,Values=vpc" --query 'Addresses[?AssociationId==null] | length(@)' --output text 2>/dev/null)

echo "  📊 VPC 리소스 상태:"
echo "  ├─ VPC ID: ${VPC_ID}"
echo "  ├─ Load Balancers: ${REMAINING_LB}"
echo "  ├─ Target Groups: ${REMAINING_TG}"
echo "  ├─ Security Groups: ${REMAINING_SG}"
echo "  ├─ Network Interfaces: ${REMAINING_ENI}"
echo "  └─ Elastic IPs (unattached): ${REMAINING_EIP}"
echo ""

TOTAL_REMAINING=$((REMAINING_LB + REMAINING_TG + REMAINING_SG + REMAINING_ENI))

if [ "$TOTAL_REMAINING" -eq 0 ]; then
  echo "✅ VPC 리소스 정리 완료!"
  echo "💡 이제 terraform destroy를 안전하게 실행할 수 있습니다."
else
  echo "⚠️  일부 리소스가 남아있습니다 (총 ${TOTAL_REMAINING}개)"
  echo "💡 terraform destroy는 계속 진행되지만, VPC 삭제 실패 시 스크립트를 다시 실행하세요."

  if [ "$REMAINING_ENI" -gt 0 ]; then
    echo ""
    echo "남아있는 ENI 목록:"
    aws ec2 describe-network-interfaces \
      --region ${REGION} \
      --filters "Name=vpc-id,Values=${VPC_ID}" \
      --query 'NetworkInterfaces[*].[NetworkInterfaceId,Description,Status]' \
      --output table 2>/dev/null
  fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
