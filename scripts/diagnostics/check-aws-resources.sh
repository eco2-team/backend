#!/bin/bash
# AWS 리소스 종합 진단 스크립트
# 
# 사용 목적:
# - 현재 AWS 계정에 남아있는 모든 프로젝트 관련 리소스 확인
# - 삭제 후 잔여 리소스 확인
# - 비용 발생 리소스 파악
#
# 사용 방법:
#   ./scripts/diagnostics/check-aws-resources.sh
#
# 예상 소요 시간: 30초 ~ 1분

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 기본 리전
AWS_REGION=${AWS_REGION:-ap-northeast-2}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 AWS 리소스 종합 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📍 리전: $AWS_REGION"
echo "📅 실행 시각: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 카운터 초기화
VPC_COUNT=0
INSTANCE_COUNT=0
CF_COUNT=0
CERT_US_COUNT=0
CERT_REGION_COUNT=0
ALB_COUNT=0
TG_COUNT=0
NAT_COUNT=0
S3_COUNT=0
EBS_COUNT=0
EIP_COUNT=0
SG_COUNT=0
ENI_COUNT=0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣ Terraform State 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Terraform State 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -d "$TERRAFORM_DIR" ]; then
    cd "$TERRAFORM_DIR"
    
    if [ -f "terraform.tfstate" ] || [ -d ".terraform" ]; then
        TF_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
        
        if [ "$TF_COUNT" -gt 0 ]; then
            echo -e "${YELLOW}⚠️  Terraform 관리 리소스: $TF_COUNT 개${NC}"
            echo ""
            terraform state list 2>/dev/null | head -20
            
            if [ "$TF_COUNT" -gt 20 ]; then
                echo "   ... (생략)"
            fi
        else
            echo -e "${GREEN}✅ Terraform State 비어있음${NC}"
        fi
    else
        echo -e "${BLUE}ℹ️  Terraform State 파일 없음${NC}"
    fi
else
    echo -e "${BLUE}ℹ️  Terraform 디렉토리 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2️⃣ VPC 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ VPC 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

VPC_COUNT=$(aws ec2 describe-vpcs \
    --filters "Name=is-default,Values=false" \
    --region $AWS_REGION \
    --query 'Vpcs | length(@)' --output text 2>/dev/null || echo "0")

if [ "$VPC_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 VPC: $VPC_COUNT 개${NC}"
    echo ""
    aws ec2 describe-vpcs \
        --filters "Name=is-default,Values=false" \
        --region $AWS_REGION \
        --query 'Vpcs[*].[VpcId, CidrBlock, Tags[?Key==`Name`].Value|[0]]' \
        --output table
else
    echo -e "${GREEN}✅ VPC 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3️⃣ EC2 인스턴스 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ EC2 인스턴스 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

INSTANCE_COUNT=$(aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running,stopped,stopping" \
    --region $AWS_REGION \
    --query 'Reservations[*].Instances[] | length(@)' --output text 2>/dev/null || echo "0")

if [ "$INSTANCE_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  실행 중인 인스턴스: $INSTANCE_COUNT 개${NC}"
    echo ""
    aws ec2 describe-instances \
        --filters "Name=instance-state-name,Values=running,stopped,stopping" \
        --region $AWS_REGION \
        --query 'Reservations[*].Instances[*].[InstanceId, State.Name, InstanceType, Tags[?Key==`Name`].Value|[0]]' \
        --output table
    
    # 비용 추정
    echo ""
    echo -e "${CYAN}💰 예상 월간 비용:${NC}"
    RUNNING_COUNT=$(aws ec2 describe-instances \
        --filters "Name=instance-state-name,Values=running" \
        --region $AWS_REGION \
        --query 'Reservations[*].Instances[] | length(@)' --output text 2>/dev/null || echo "0")
    
    echo "   - 실행 중: $RUNNING_COUNT 개"
    echo "   - 대략적 비용: \$$(($RUNNING_COUNT * 30)) ~ \$$(($RUNNING_COUNT * 80)) / 월"
else
    echo -e "${GREEN}✅ EC2 인스턴스 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4️⃣ CloudFront Distribution 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ CloudFront Distribution 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

CF_COUNT=$(aws cloudfront list-distributions \
    --query "DistributionList.Items | length(@)" --output text 2>/dev/null || echo "0")

if [ "$CF_COUNT" != "0" ] && [ "$CF_COUNT" != "None" ]; then
    echo -e "${YELLOW}⚠️  남은 Distribution: $CF_COUNT 개${NC}"
    echo ""
    aws cloudfront list-distributions \
        --query "DistributionList.Items[*].[Id, Status, Enabled, DomainName, Comment]" \
        --output table 2>/dev/null
    
    echo ""
    echo -e "${CYAN}💰 예상 월간 비용:${NC}"
    echo "   - CloudFront: \$10 ~ \$50 / 월 (트래픽에 따라 변동)"
else
    echo -e "${GREEN}✅ CloudFront Distribution 없음${NC}"
    CF_COUNT=0
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5️⃣ ACM Certificate (us-east-1) 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ ACM Certificate (us-east-1) 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

CERT_US_COUNT=$(aws acm list-certificates \
    --region us-east-1 \
    --query "CertificateSummaryList | length(@)" --output text 2>/dev/null || echo "0")

if [ "$CERT_US_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Certificate: $CERT_US_COUNT 개${NC}"
    echo ""
    aws acm list-certificates \
        --region us-east-1 \
        --query "CertificateSummaryList[*].[DomainName, Status, CertificateArn]" \
        --output table 2>/dev/null
    
    # 사용 현황 확인
    echo ""
    echo -e "${CYAN}📋 Certificate 사용 현황:${NC}"
    aws acm list-certificates --region us-east-1 --output json 2>/dev/null | \
        jq -r '.CertificateSummaryList[]? | .CertificateArn' | while read cert_arn; do
        IN_USE=$(aws acm describe-certificate \
            --certificate-arn "$cert_arn" \
            --region us-east-1 \
            --query 'Certificate.InUseBy | length(@)' --output text 2>/dev/null || echo "0")
        DOMAIN=$(aws acm describe-certificate \
            --certificate-arn "$cert_arn" \
            --region us-east-1 \
            --query 'Certificate.DomainName' --output text 2>/dev/null || echo "unknown")
        
        if [ "$IN_USE" -gt 0 ]; then
            echo "   - $DOMAIN: 사용 중 ($IN_USE 개 리소스)"
        else
            echo "   - $DOMAIN: 미사용"
        fi
    done
else
    echo -e "${GREEN}✅ ACM Certificate 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6️⃣ ACM Certificate (리전) 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ ACM Certificate ($AWS_REGION) 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

CERT_REGION_COUNT=$(aws acm list-certificates \
    --region $AWS_REGION \
    --query "CertificateSummaryList | length(@)" --output text 2>/dev/null || echo "0")

if [ "$CERT_REGION_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Certificate: $CERT_REGION_COUNT 개${NC}"
    echo ""
    aws acm list-certificates \
        --region $AWS_REGION \
        --query "CertificateSummaryList[*].[DomainName, Status]" \
        --output table 2>/dev/null
else
    echo -e "${GREEN}✅ ACM Certificate 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7️⃣ Load Balancer 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ Load Balancer 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ALB_COUNT=$(aws elbv2 describe-load-balancers \
    --region $AWS_REGION \
    --query "LoadBalancers | length(@)" --output text 2>/dev/null || echo "0")

if [ "$ALB_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Load Balancer: $ALB_COUNT 개${NC}"
    echo ""
    aws elbv2 describe-load-balancers \
        --region $AWS_REGION \
        --query "LoadBalancers[*].[LoadBalancerName, State.Code, Type, VpcId]" \
        --output table 2>/dev/null
    
    echo ""
    echo -e "${CYAN}💰 예상 월간 비용:${NC}"
    echo "   - ALB: \$$(($ALB_COUNT * 20)) ~ \$$(($ALB_COUNT * 40)) / 월"
else
    echo -e "${GREEN}✅ Load Balancer 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8️⃣ Target Groups 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ Target Groups 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TG_COUNT=$(aws elbv2 describe-target-groups \
    --region $AWS_REGION \
    --query "TargetGroups | length(@)" --output text 2>/dev/null || echo "0")

if [ "$TG_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Target Groups: $TG_COUNT 개${NC}"
    echo ""
    aws elbv2 describe-target-groups \
        --region $AWS_REGION \
        --query "TargetGroups[*].[TargetGroupName, Protocol, Port, VpcId]" \
        --output table 2>/dev/null
else
    echo -e "${GREEN}✅ Target Groups 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9️⃣ NAT Gateway 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9️⃣ NAT Gateway 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

NAT_COUNT=$(aws ec2 describe-nat-gateways \
    --filter "Name=state,Values=available,pending,deleting" \
    --region $AWS_REGION \
    --query "NatGateways | length(@)" --output text 2>/dev/null || echo "0")

if [ "$NAT_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 NAT Gateway: $NAT_COUNT 개${NC}"
    echo ""
    aws ec2 describe-nat-gateways \
        --filter "Name=state,Values=available,pending,deleting" \
        --region $AWS_REGION \
        --query "NatGateways[*].[NatGatewayId, State, VpcId]" \
        --output table 2>/dev/null
    
    echo ""
    echo -e "${CYAN}💰 예상 월간 비용:${NC}"
    echo "   - NAT Gateway: \$$(($NAT_COUNT * 35)) ~ \$$(($NAT_COUNT * 50)) / 월"
else
    echo -e "${GREEN}✅ NAT Gateway 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔟 S3 Bucket 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔟 S3 Bucket 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

S3_COUNT=$(aws s3api list-buckets \
    --query "Buckets[?starts_with(Name, 'prod-sesacthon') || starts_with(Name, 'sesacthon')] | length(@)" \
    --output text 2>/dev/null || echo "0")

if [ "$S3_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  프로젝트 관련 Bucket: $S3_COUNT 개${NC}"
    echo ""
    
    aws s3api list-buckets \
        --query "Buckets[?starts_with(Name, 'prod-sesacthon') || starts_with(Name, 'sesacthon')].[Name, CreationDate]" \
        --output table 2>/dev/null
    
    # 버킷 크기 확인
    echo ""
    echo -e "${CYAN}📦 버킷 내용:${NC}"
    aws s3api list-buckets --output json 2>/dev/null | \
        jq -r '.Buckets[]? | select(.Name | startswith("sesacthon") or startswith("prod-sesacthon")) | .Name' | \
        while read bucket; do
        OBJECT_COUNT=$(aws s3 ls "s3://$bucket" --recursive 2>/dev/null | wc -l | tr -d ' ')
        if [ "$OBJECT_COUNT" -gt 0 ]; then
            echo "   - $bucket: $OBJECT_COUNT 개 객체"
        else
            echo "   - $bucket: 비어있음"
        fi
    done
else
    echo -e "${GREEN}✅ S3 Bucket 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣1️⃣ EBS 볼륨 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣1️⃣ EBS 볼륨 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

EBS_COUNT=$(aws ec2 describe-volumes \
    --region $AWS_REGION \
    --query "Volumes[?State=='available' || State=='error'] | length(@)" \
    --output text 2>/dev/null || echo "0")

if [ "$EBS_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 EBS 볼륨: $EBS_COUNT 개${NC}"
    echo ""
    aws ec2 describe-volumes \
        --region $AWS_REGION \
        --query "Volumes[?State=='available' || State=='error'].[VolumeId, Size, State, VolumeType, Tags[?Key=='Name'].Value|[0]]" \
        --output table 2>/dev/null
    
    # 총 용량 계산
    TOTAL_SIZE=$(aws ec2 describe-volumes \
        --region $AWS_REGION \
        --query "sum(Volumes[?State=='available' || State=='error'].Size)" \
        --output text 2>/dev/null || echo "0")
    
    echo ""
    echo -e "${CYAN}💰 예상 월간 비용:${NC}"
    echo "   - 총 용량: ${TOTAL_SIZE}GB"
    echo "   - EBS gp3: \$$(echo "$TOTAL_SIZE * 0.08" | bc) / 월"
else
    echo -e "${GREEN}✅ 남은 EBS 볼륨 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣2️⃣ Elastic IP 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣2️⃣ Elastic IP 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

EIP_COUNT=$(aws ec2 describe-addresses \
    --region $AWS_REGION \
    --query "Addresses | length(@)" --output text 2>/dev/null || echo "0")

if [ "$EIP_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Elastic IP: $EIP_COUNT 개${NC}"
    echo ""
    aws ec2 describe-addresses \
        --region $AWS_REGION \
        --query "Addresses[*].[AllocationId, PublicIp, AssociationId, Tags[?Key=='Name'].Value|[0]]" \
        --output table 2>/dev/null
    
    UNATTACHED=$(aws ec2 describe-addresses \
        --region $AWS_REGION \
        --query "Addresses[?AssociationId==null] | length(@)" --output text 2>/dev/null || echo "0")
    
    if [ "$UNATTACHED" -gt 0 ]; then
        echo ""
        echo -e "${CYAN}💰 예상 월간 비용:${NC}"
        echo "   - 미연결 EIP: \$$(echo "$UNATTACHED * 3.6" | bc) / 월"
    fi
else
    echo -e "${GREEN}✅ Elastic IP 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣3️⃣ Security Groups 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣3️⃣ Security Groups 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

SG_COUNT=$(aws ec2 describe-security-groups \
    --region $AWS_REGION \
    --query "SecurityGroups[?GroupName!='default'] | length(@)" --output text 2>/dev/null || echo "0")

if [ "$SG_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 Security Groups: $SG_COUNT 개 (default 제외)${NC}"
    echo ""
    aws ec2 describe-security-groups \
        --region $AWS_REGION \
        --query "SecurityGroups[?GroupName!='default'].[GroupId, GroupName, VpcId]" \
        --output table 2>/dev/null | head -25
    
    if [ "$SG_COUNT" -gt 20 ]; then
        echo "   ... (생략)"
    fi
else
    echo -e "${GREEN}✅ 추가 Security Groups 없음 (default만 존재)${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1️⃣4️⃣ ENI 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣4️⃣ ENI (Network Interface) 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ENI_COUNT=$(aws ec2 describe-network-interfaces \
    --region $AWS_REGION \
    --query "NetworkInterfaces[?Status=='available'] | length(@)" --output text 2>/dev/null || echo "0")

if [ "$ENI_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  남은 ENI: $ENI_COUNT 개${NC}"
    echo ""
    aws ec2 describe-network-interfaces \
        --region $AWS_REGION \
        --query "NetworkInterfaces[?Status=='available'].[NetworkInterfaceId, Status, Description]" \
        --output table 2>/dev/null
else
    echo -e "${GREEN}✅ 남은 ENI 없음${NC}"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 종합 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TOTAL=$((VPC_COUNT + INSTANCE_COUNT + CF_COUNT + CERT_US_COUNT + CERT_REGION_COUNT + ALB_COUNT + TG_COUNT + NAT_COUNT + S3_COUNT + EBS_COUNT + EIP_COUNT + SG_COUNT + ENI_COUNT))

if [ "$TOTAL" -eq 0 ]; then
    echo -e "${GREEN}✅ 모든 리소스가 삭제되었습니다!${NC}"
    echo ""
    echo "💰 월 예상 비용: \$0"
else
    echo -e "${YELLOW}⚠️  남은 리소스: $TOTAL 개${NC}"
    echo ""
    echo "📝 리소스 분류:"
    
    [ "$VPC_COUNT" -gt 0 ] && echo "   - VPC: $VPC_COUNT 개"
    [ "$INSTANCE_COUNT" -gt 0 ] && echo "   - EC2 인스턴스: $INSTANCE_COUNT 개"
    [ "$CF_COUNT" -gt 0 ] && echo "   - CloudFront: $CF_COUNT 개"
    [ "$CERT_US_COUNT" -gt 0 ] && echo "   - ACM Certificate (us-east-1): $CERT_US_COUNT 개"
    [ "$CERT_REGION_COUNT" -gt 0 ] && echo "   - ACM Certificate (리전): $CERT_REGION_COUNT 개"
    [ "$ALB_COUNT" -gt 0 ] && echo "   - Load Balancer: $ALB_COUNT 개"
    [ "$TG_COUNT" -gt 0 ] && echo "   - Target Groups: $TG_COUNT 개"
    [ "$NAT_COUNT" -gt 0 ] && echo "   - NAT Gateway: $NAT_COUNT 개"
    [ "$S3_COUNT" -gt 0 ] && echo "   - S3 Bucket: $S3_COUNT 개"
    [ "$EBS_COUNT" -gt 0 ] && echo "   - EBS 볼륨: $EBS_COUNT 개"
    [ "$EIP_COUNT" -gt 0 ] && echo "   - Elastic IP: $EIP_COUNT 개"
    [ "$SG_COUNT" -gt 0 ] && echo "   - Security Groups: $SG_COUNT 개"
    [ "$ENI_COUNT" -gt 0 ] && echo "   - ENI: $ENI_COUNT 개"
    
    echo ""
    echo -e "${CYAN}💡 권장 조치:${NC}"
    
    if [ "$INSTANCE_COUNT" -gt 0 ]; then
        echo "   1. EC2 인스턴스 중지 또는 종료"
    fi
    
    if [ "$NAT_COUNT" -gt 0 ]; then
        echo "   2. NAT Gateway 삭제 (비용 절감 효과 큼)"
    fi
    
    if [ "$ALB_COUNT" -gt 0 ]; then
        echo "   3. Load Balancer 삭제"
    fi
    
    if [ "$CF_COUNT" -gt 0 ]; then
        echo "   4. CloudFront Distribution 비활성화 후 삭제"
    fi
    
    if [ "$VPC_COUNT" -gt 0 ]; then
        echo "   5. VPC 및 관련 리소스 정리"
    fi
    
    echo ""
    echo "🗑️  강제 삭제 스크립트:"
    echo "   ./scripts/utilities/force-destroy-all.sh"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""


