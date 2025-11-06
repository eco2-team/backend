#!/bin/bash
# 실제 VPC 기반 강제 리소스 정리 스크립트
# State 파일 없이 AWS CLI로 직접 삭제

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔥 강제 리소스 정리 (State 파일 없이)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 실제 VPC ID (AWS에서 확인한 값)
VPC_ID="vpc-08294cf2cbb7c9f24"
AWS_REGION="ap-northeast-2"

echo "📋 VPC ID: $VPC_ID"
echo "🌏 Region: $AWS_REGION"
echo ""

# 자동 실행 모드
echo "🤖 자동 모드로 실행 중..."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ EC2 인스턴스 종료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# EC2 인스턴스 확인
EC2_INSTANCES=$(aws ec2 describe-instances \
    --filters "Name=vpc-id,Values=$VPC_ID" \
              "Name=instance-state-name,Values=running,stopped,stopping,pending" \
    --region "$AWS_REGION" \
    --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0]]' \
    --output text 2>/dev/null || echo "")

if [ -n "$EC2_INSTANCES" ]; then
    echo "⚠️  실행 중인 EC2 인스턴스 발견:"
    echo "$EC2_INSTANCES" | while read instance_id name; do
        echo "  - $name ($instance_id)"
    done
    
    EC2_IDS=$(echo "$EC2_INSTANCES" | awk '{print $1}' | tr '\n' ' ')
    
    echo ""
    echo "  🗑️  EC2 인스턴스 종료 중..."
    aws ec2 terminate-instances \
        --instance-ids $EC2_IDS \
        --region "$AWS_REGION" >/dev/null 2>&1
    
    echo "  ⏳ EC2 인스턴스 종료 대기 중... (최대 3분)"
    
    MAX_WAIT=90
    WAIT_COUNT=0
    
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        REMAINING=$(aws ec2 describe-instances \
            --instance-ids $EC2_IDS \
            --region "$AWS_REGION" \
            --query 'Reservations[*].Instances[?State.Name!=`terminated`].InstanceId' \
            --output text 2>/dev/null || echo "")
        
        if [ -z "$REMAINING" ]; then
            echo "     ✅ 모든 EC2 인스턴스 종료 완료 (${WAIT_COUNT}초 소요)"
            break
        fi
        
        if [ $((WAIT_COUNT % 15)) -eq 0 ]; then
            REMAINING_COUNT=$(echo "$REMAINING" | wc -w | tr -d ' ')
            echo "     ⏳ 대기 중... (${WAIT_COUNT}초 경과, 남은 인스턴스: ${REMAINING_COUNT}개)"
        fi
        
        sleep 3
        WAIT_COUNT=$((WAIT_COUNT + 3))
    done
else
    echo "  ✅ 실행 중인 EC2 인스턴스 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Load Balancer 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ALB/NLB 확인 및 삭제
ALB_ARNS=$(aws elbv2 describe-load-balancers \
    --region "$AWS_REGION" \
    --query "LoadBalancers[?VpcId==\`$VPC_ID\`].LoadBalancerArn" \
    --output text 2>/dev/null || echo "")

if [ -n "$ALB_ARNS" ]; then
    echo "⚠️  Load Balancer 발견:"
    for alb_arn in $ALB_ARNS; do
        ALB_NAME=$(aws elbv2 describe-load-balancers \
            --load-balancer-arns "$alb_arn" \
            --region "$AWS_REGION" \
            --query 'LoadBalancers[0].LoadBalancerName' \
            --output text 2>/dev/null)
        echo "  - $ALB_NAME"
        echo "    🗑️  삭제 중..."
        aws elbv2 delete-load-balancer \
            --load-balancer-arn "$alb_arn" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
    echo "  ⏳ ALB 삭제 대기 (30초)..."
    sleep 30
else
    echo "  ✅ Load Balancer 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Target Groups 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TG_ARNS=$(aws elbv2 describe-target-groups \
    --region "$AWS_REGION" \
    --query "TargetGroups[?VpcId==\`$VPC_ID\`].TargetGroupArn" \
    --output text 2>/dev/null || echo "")

if [ -n "$TG_ARNS" ]; then
    echo "⚠️  Target Groups 발견:"
    for tg_arn in $TG_ARNS; do
        echo "  - $tg_arn"
        aws elbv2 delete-target-group \
            --target-group-arn "$tg_arn" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
    sleep 5
else
    echo "  ✅ Target Groups 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ NAT Gateway 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

NAT_GW_IDS=$(aws ec2 describe-nat-gateways \
    --filter "Name=vpc-id,Values=$VPC_ID" "Name=state,Values=available,pending" \
    --region "$AWS_REGION" \
    --query 'NatGateways[*].NatGatewayId' \
    --output text 2>/dev/null || echo "")

if [ -n "$NAT_GW_IDS" ]; then
    echo "⚠️  NAT Gateway 발견 (삭제 후 3-5분 소요):"
    for nat_gw in $NAT_GW_IDS; do
        echo "  - $nat_gw"
        aws ec2 delete-nat-gateway \
            --nat-gateway-id "$nat_gw" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
    echo "  ⏳ NAT Gateway 삭제 시작 (백그라운드에서 3-5분 소요)"
    sleep 10
else
    echo "  ✅ NAT Gateway 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ EBS 볼륨 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 사용 가능한 EBS 볼륨 삭제
VOLUMES=$(aws ec2 describe-volumes \
    --filters "Name=availability-zone,Values=${AWS_REGION}*" \
    --region "$AWS_REGION" \
    --query 'Volumes[?State==`available`].VolumeId' \
    --output text 2>/dev/null || echo "")

if [ -n "$VOLUMES" ]; then
    echo "⚠️  사용 가능한 EBS 볼륨 발견:"
    for vol in $VOLUMES; do
        SIZE=$(aws ec2 describe-volumes --volume-ids "$vol" --region "$AWS_REGION" \
            --query 'Volumes[0].Size' --output text 2>/dev/null)
        echo "  - $vol (${SIZE}GB)"
        aws ec2 delete-volume --volume-id "$vol" --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ EBS 볼륨 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ Elastic IP 해제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

EIP_ALLOCS=$(aws ec2 describe-addresses \
    --filters "Name=domain,Values=vpc" \
    --region "$AWS_REGION" \
    --query 'Addresses[*].AllocationId' \
    --output text 2>/dev/null || echo "")

if [ -n "$EIP_ALLOCS" ]; then
    echo "⚠️  Elastic IP 발견:"
    for alloc in $EIP_ALLOCS; do
        PUBLIC_IP=$(aws ec2 describe-addresses --allocation-ids "$alloc" --region "$AWS_REGION" \
            --query 'Addresses[0].PublicIp' --output text 2>/dev/null)
        echo "  - $alloc ($PUBLIC_IP)"
        aws ec2 release-address --allocation-id "$alloc" --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ Elastic IP 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ Network Interfaces (ENI) 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ENI_IDS=$(aws ec2 describe-network-interfaces \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'NetworkInterfaces[?Status==`available`].NetworkInterfaceId' \
    --output text 2>/dev/null || echo "")

if [ -n "$ENI_IDS" ]; then
    echo "⚠️  사용 가능한 ENI 발견:"
    for eni in $ENI_IDS; do
        echo "  - $eni"
        aws ec2 delete-network-interface \
            --network-interface-id "$eni" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ ENI 없음"
fi

echo ""
echo "⏳ 리소스 삭제 완료 대기 (20초)..."
sleep 20

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ Security Groups 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Security Groups 규칙 먼저 삭제
SG_IDS=$(aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'SecurityGroups[?GroupName!=`default`].GroupId' \
    --output text 2>/dev/null || echo "")

if [ -n "$SG_IDS" ]; then
    echo "⚠️  Security Groups 발견 (규칙 먼저 삭제):"
    
    for sg in $SG_IDS; do
        SG_NAME=$(aws ec2 describe-security-groups --group-ids "$sg" --region "$AWS_REGION" \
            --query 'SecurityGroups[0].GroupName' --output text 2>/dev/null)
        echo "  - $sg ($SG_NAME)"
        
        # Ingress 규칙 삭제
        INGRESS=$(aws ec2 describe-security-groups --group-ids "$sg" --region "$AWS_REGION" \
            --query 'SecurityGroups[0].IpPermissions' --output json 2>/dev/null)
        
        if [ "$INGRESS" != "[]" ] && [ "$INGRESS" != "null" ]; then
            aws ec2 revoke-security-group-ingress \
                --group-id "$sg" \
                --ip-permissions "$INGRESS" \
                --region "$AWS_REGION" >/dev/null 2>&1 || true
        fi
        
        # Egress 규칙 삭제
        EGRESS=$(aws ec2 describe-security-groups --group-ids "$sg" --region "$AWS_REGION" \
            --query 'SecurityGroups[0].IpPermissionsEgress' --output json 2>/dev/null)
        
        if [ "$EGRESS" != "[]" ] && [ "$EGRESS" != "null" ]; then
            aws ec2 revoke-security-group-egress \
                --group-id "$sg" \
                --ip-permissions "$EGRESS" \
                --region "$AWS_REGION" >/dev/null 2>&1 || true
        fi
    done
    
    echo "  ⏳ Security Group 규칙 삭제 대기 (10초)..."
    sleep 10
    
    # Security Groups 삭제
    echo ""
    echo "  🗑️  Security Groups 삭제 중..."
    for sg in $SG_IDS; do
        aws ec2 delete-security-group \
            --group-id "$sg" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ 추가 Security Groups 없음 (default만 존재)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9️⃣ Subnets 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'Subnets[*].SubnetId' \
    --output text 2>/dev/null || echo "")

if [ -n "$SUBNET_IDS" ]; then
    echo "⚠️  Subnets 발견:"
    for subnet in $SUBNET_IDS; do
        SUBNET_NAME=$(aws ec2 describe-subnets --subnet-ids "$subnet" --region "$AWS_REGION" \
            --query 'Subnets[0].Tags[?Key==`Name`].Value|[0]' --output text 2>/dev/null || echo "unnamed")
        echo "  - $subnet ($SUBNET_NAME)"
        aws ec2 delete-subnet \
            --subnet-id "$subnet" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ Subnets 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔟 Internet Gateway 분리 및 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

IGW_IDS=$(aws ec2 describe-internet-gateways \
    --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'InternetGateways[*].InternetGatewayId' \
    --output text 2>/dev/null || echo "")

if [ -n "$IGW_IDS" ]; then
    echo "⚠️  Internet Gateway 발견:"
    for igw in $IGW_IDS; do
        echo "  - $igw"
        echo "    🔗 VPC에서 분리 중..."
        aws ec2 detach-internet-gateway \
            --internet-gateway-id "$igw" \
            --vpc-id "$VPC_ID" \
            --region "$AWS_REGION" 2>/dev/null || true
        echo "    🗑️  삭제 중..."
        aws ec2 delete-internet-gateway \
            --internet-gateway-id "$igw" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ Internet Gateway 없음"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣1️⃣ Route Tables 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

RT_IDS=$(aws ec2 describe-route-tables \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region "$AWS_REGION" \
    --query 'RouteTables[?Associations[0].Main!=`true`].RouteTableId' \
    --output text 2>/dev/null || echo "")

if [ -n "$RT_IDS" ]; then
    echo "⚠️  Route Tables 발견 (Main 제외):"
    for rt in $RT_IDS; do
        echo "  - $rt"
        aws ec2 delete-route-table \
            --route-table-id "$rt" \
            --region "$AWS_REGION" 2>/dev/null || true
    done
else
    echo "  ✅ 추가 Route Tables 없음 (Main만 존재)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣2️⃣ VPC 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "⏳ 최종 대기 (10초)..."
sleep 10

echo "🗑️  VPC 삭제 시도: $VPC_ID"
if aws ec2 delete-vpc --vpc-id "$VPC_ID" --region "$AWS_REGION" 2>&1; then
    echo "  ✅ VPC 삭제 성공!"
else
    echo "  ⚠️  VPC 삭제 실패 - 남은 종속 리소스 확인 필요"
    echo ""
    echo "  남은 리소스 확인:"
    echo "  - ENI: $(aws ec2 describe-network-interfaces --filters "Name=vpc-id,Values=$VPC_ID" --region "$AWS_REGION" --query 'NetworkInterfaces[*].NetworkInterfaceId' --output text 2>/dev/null | wc -w)"
    echo "  - Subnets: $(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region "$AWS_REGION" --query 'Subnets[*].SubnetId' --output text 2>/dev/null | wc -w)"
    echo "  - Security Groups: $(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" --region "$AWS_REGION" --query 'SecurityGroups[*].GroupId' --output text 2>/dev/null | wc -w)"
    echo "  - Route Tables: $(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" --region "$AWS_REGION" --query 'RouteTables[*].RouteTableId' --output text 2>/dev/null | wc -w)"
    echo ""
    echo "  수동 정리 후 다시 시도하세요."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 리소스 정리 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

