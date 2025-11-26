#!/bin/bash
# Security Group 종속성 진단 스크립트

set -e

REGION=${AWS_REGION:-ap-northeast-2}
MASTER_SG_ID="sg-0afdc5528d5cf7d1c"
WORKER_SG_ID="sg-06d0aec7f41806b51"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Security Group 종속성 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

check_sg_dependencies() {
  local SG_ID=$1
  local SG_NAME=$2

  echo "📌 Security Group: ${SG_NAME} (${SG_ID})"
  echo ""

  # 1. EC2 인스턴스 확인
  echo "1️⃣  EC2 인스턴스 확인:"
  EC2_COUNT=$(aws ec2 describe-instances \
    --region ${REGION} \
    --filters "Name=instance.group-id,Values=${SG_ID}" "Name=instance-state-name,Values=running,stopped,stopping,pending" \
    --query 'Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`Name`].Value|[0]]' \
    --output text 2>/dev/null | wc -l | tr -d ' ')

  if [ "$EC2_COUNT" -gt 0 ]; then
    echo "  ⚠️  연결된 EC2: ${EC2_COUNT}개"
    aws ec2 describe-instances \
      --region ${REGION} \
      --filters "Name=instance.group-id,Values=${SG_ID}" "Name=instance-state-name,Values=running,stopped,stopping,pending" \
      --query 'Reservations[*].Instances[*].[InstanceId,State.Name,Tags[?Key==`Name`].Value|[0]]' \
      --output table 2>/dev/null
  else
    echo "  ✅ EC2 인스턴스 없음"
  fi
  echo ""

  # 2. Network Interface (ENI) 확인
  echo "2️⃣  Network Interface (ENI) 확인:"
  ENI_COUNT=$(aws ec2 describe-network-interfaces \
    --region ${REGION} \
    --filters "Name=group-id,Values=${SG_ID}" \
    --query 'NetworkInterfaces[*].[NetworkInterfaceId,Description,Status,Attachment.InstanceId]' \
    --output text 2>/dev/null | wc -l | tr -d ' ')

  if [ "$ENI_COUNT" -gt 0 ]; then
    echo "  ⚠️  연결된 ENI: ${ENI_COUNT}개"
    aws ec2 describe-network-interfaces \
      --region ${REGION} \
      --filters "Name=group-id,Values=${SG_ID}" \
      --query 'NetworkInterfaces[*].[NetworkInterfaceId,Description,Status,Attachment.InstanceId]' \
      --output table 2>/dev/null

    # ENI 삭제 가능 여부 확인
    echo ""
    echo "  ENI 상세 정보:"
    aws ec2 describe-network-interfaces \
      --region ${REGION} \
      --filters "Name=group-id,Values=${SG_ID}" \
      --query 'NetworkInterfaces[*].[NetworkInterfaceId,RequesterManaged,Attachment.DeleteOnTermination,InterfaceType]' \
      --output table 2>/dev/null
  else
    echo "  ✅ ENI 없음"
  fi
  echo ""

  # 3. Load Balancer 확인
  echo "3️⃣  Load Balancer 확인:"
  LB_COUNT=$(aws elbv2 describe-load-balancers \
    --region ${REGION} \
    --query "LoadBalancers[?contains(SecurityGroups, '${SG_ID}')] | length(@)" \
    --output text 2>/dev/null)

  if [ "$LB_COUNT" -gt 0 ]; then
    echo "  ⚠️  연결된 Load Balancer: ${LB_COUNT}개"
    aws elbv2 describe-load-balancers \
      --region ${REGION} \
      --query "LoadBalancers[?contains(SecurityGroups, '${SG_ID}')].[LoadBalancerName,Type,State.Code]" \
      --output table 2>/dev/null
  else
    echo "  ✅ Load Balancer 없음"
  fi
  echo ""

  # 4. RDS 인스턴스 확인
  echo "4️⃣  RDS 인스턴스 확인:"
  RDS_COUNT=$(aws rds describe-db-instances \
    --region ${REGION} \
    --query "DBInstances[?VpcSecurityGroups[?VpcSecurityGroupId=='${SG_ID}']] | length(@)" \
    --output text 2>/dev/null)

  if [ "$RDS_COUNT" -gt 0 ]; then
    echo "  ⚠️  연결된 RDS: ${RDS_COUNT}개"
    aws rds describe-db-instances \
      --region ${REGION} \
      --query "DBInstances[?VpcSecurityGroups[?VpcSecurityGroupId=='${SG_ID}']].[DBInstanceIdentifier,DBInstanceStatus]" \
      --output table 2>/dev/null
  else
    echo "  ✅ RDS 인스턴스 없음"
  fi
  echo ""

  # 5. Lambda 함수 확인
  echo "5️⃣  Lambda 함수 확인:"
  LAMBDA_FUNCS=$(aws lambda list-functions \
    --region ${REGION} \
    --query "Functions[?VpcConfig.SecurityGroupIds && contains(VpcConfig.SecurityGroupIds, '${SG_ID}')].FunctionName" \
    --output text 2>/dev/null)

  if [ -n "$LAMBDA_FUNCS" ]; then
    echo "  ⚠️  연결된 Lambda 함수:"
    echo "$LAMBDA_FUNCS" | tr '\t' '\n' | while read func; do
      echo "    - $func"
    done
  else
    echo "  ✅ Lambda 함수 없음"
  fi
  echo ""

  # 6. 다른 Security Group 규칙에서의 참조 확인
  echo "6️⃣  다른 Security Group의 규칙에서 참조 확인:"
  REF_COUNT=$(aws ec2 describe-security-groups \
    --region ${REGION} \
    --query "SecurityGroups[?IpPermissions[?UserIdGroupPairs[?GroupId=='${SG_ID}']] || IpPermissionsEgress[?UserIdGroupPairs[?GroupId=='${SG_ID}']]] | length(@)" \
    --output text 2>/dev/null)

  if [ "$REF_COUNT" -gt 0 ]; then
    echo "  ⚠️  ${SG_ID}를 참조하는 다른 Security Group: ${REF_COUNT}개"
    aws ec2 describe-security-groups \
      --region ${REGION} \
      --query "SecurityGroups[?IpPermissions[?UserIdGroupPairs[?GroupId=='${SG_ID}']] || IpPermissionsEgress[?UserIdGroupPairs[?GroupId=='${SG_ID}']]].[GroupId,GroupName]" \
      --output table 2>/dev/null
  else
    echo "  ✅ 다른 Security Group에서 참조 없음"
  fi
  echo ""

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
}

# Master Security Group 확인
check_sg_dependencies "${MASTER_SG_ID}" "Master"

# Worker Security Group 확인
check_sg_dependencies "${WORKER_SG_ID}" "Worker"

echo ""
echo "✅ 진단 완료"
echo ""
echo "💡 다음 단계:"
echo "   1. 위에서 발견된 종속 리소스를 먼저 삭제하세요"
echo "   2. 또는 scripts/cleanup-vpc-resources.sh 스크립트를 실행하세요"
echo ""
