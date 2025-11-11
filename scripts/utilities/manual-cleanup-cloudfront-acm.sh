#!/bin/bash
# CloudFront Distribution 및 ACM Certificate 수동 삭제 스크립트
# 
# 사용 목적:
# - destroy-with-cleanup.sh가 CloudFront를 검색하지 못했을 때
# - ACM Certificate가 CloudFront 사용 중으로 삭제 안 될 때
#
# 사용 방법:
#   ./scripts/utilities/manual-cleanup-cloudfront-acm.sh
#
# 예상 소요 시간: 8-10분

set -e

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIST_ID="${CLOUDFRONT_DIST_ID:-E1GGDPUBLRQG59}"
CERT_ARN="${ACM_CERT_ARN:-arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 함수 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# CloudFront Distribution ID 자동 검색
find_cloudfront_distributions() {
    echo "🔍 CloudFront Distribution 검색 중..."
    
    # 1. S3 버킷 기반 검색
    local s3_dists=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?contains(Origins.Items[].DomainName, 'sesacthon-images')].Id" \
        --output text 2>/dev/null || echo "")
    
    # 2. ACM Certificate 기반 검색
    local acm_dists=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?contains(to_string(ViewerCertificate.ACMCertificateArn), 'images') || contains(to_string(Aliases.Items), 'images')].Id" \
        --output text 2>/dev/null || echo "")
    
    # 중복 제거 및 병합
    local all_dists=$(echo "$s3_dists $acm_dists" | tr ' ' '\n' | sort -u | grep -v '^$' | tr '\n' ' ')
    
    if [ -n "$all_dists" ]; then
        echo "   발견된 Distribution: $all_dists"
        DIST_ID=$(echo "$all_dists" | awk '{print $1}')  # 첫 번째 사용
    else
        echo "   ⚠️  자동 검색 실패. 수동으로 Distribution ID를 입력하세요."
        read -p "   Distribution ID: " DIST_ID
    fi
}

# ACM Certificate ARN 자동 검색
find_acm_certificate() {
    echo "🔍 ACM Certificate 검색 중..."
    
    local cert=$(aws acm list-certificates \
        --region us-east-1 \
        --query "CertificateSummaryList[?contains(DomainName, 'images')].CertificateArn" \
        --output text 2>/dev/null | head -1)
    
    if [ -n "$cert" ]; then
        echo "   발견된 Certificate: $cert"
        CERT_ARN="$cert"
    else
        echo "   ⚠️  자동 검색 실패."
    fi
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 로직
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 CloudFront Distribution 수동 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# CloudFront Distribution ID가 지정되지 않은 경우 자동 검색
if [ "$DIST_ID" = "E1GGDPUBLRQG59" ]; then
    find_cloudfront_distributions
fi

# ACM Certificate ARN이 기본값인 경우 자동 검색
if [[ "$CERT_ARN" == *"b34e6013-babe-4495-88f6-77f4d9bdd39f"* ]]; then
    find_acm_certificate
fi

echo ""
echo "📋 처리할 리소스:"
echo "   CloudFront Distribution ID: $DIST_ID"
echo "   ACM Certificate ARN: $CERT_ARN"
echo ""

# 확인 프롬프트
read -p "⚠️  계속 진행하시겠습니까? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "❌ 취소되었습니다."
    exit 0
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1단계: CloudFront 현재 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "1️⃣ CloudFront 현재 상태 확인..."

CURRENT_STATE=$(aws cloudfront get-distribution --id "$DIST_ID" \
    --query 'Distribution.{Status:Status,Enabled:DistributionConfig.Enabled}' \
    --output json 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "   ❌ CloudFront Distribution을 찾을 수 없습니다: $DIST_ID"
    exit 1
fi

CURRENT_ENABLED=$(echo "$CURRENT_STATE" | jq -r '.Enabled')
CURRENT_STATUS=$(echo "$CURRENT_STATE" | jq -r '.Status')

echo "   현재 상태:"
echo "     - Enabled: $CURRENT_ENABLED"
echo "     - Status: $CURRENT_STATUS"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2단계: CloudFront Disable
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if [ "$CURRENT_ENABLED" = "true" ]; then
    echo "2️⃣ CloudFront Disable 중..."
    
    CONFIG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --output json)
    ETAG=$(echo "$CONFIG" | jq -r '.ETag')
    NEW_CONFIG=$(echo "$CONFIG" | jq '.DistributionConfig | .Enabled = false')
    
    aws cloudfront update-distribution \
        --id "$DIST_ID" \
        --if-match "$ETAG" \
        --distribution-config "$NEW_CONFIG" \
        >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "   ✅ CloudFront Disable 요청 성공"
    else
        echo "   ❌ CloudFront Disable 실패"
        exit 1
    fi
    
    # Disabled 상태 대기
    echo ""
    echo "3️⃣ CloudFront Disabled 상태 전환 대기 중..."
    echo "   (예상 시간: 2-5분)"
    
    MAX_WAIT=300  # 5분
    WAIT_COUNT=0
    
    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        if [ $((WAIT_COUNT % 30)) -eq 0 ]; then
            echo "   ⏳ 대기 중... (${WAIT_COUNT}초 경과)"
        fi
        
        sleep 10
        WAIT_COUNT=$((WAIT_COUNT + 10))
        
        CURRENT_ENABLED=$(aws cloudfront get-distribution --id "$DIST_ID" \
            --query 'Distribution.DistributionConfig.Enabled' \
            --output text 2>/dev/null)
        
        if [ "$CURRENT_ENABLED" = "False" ]; then
            echo "   ✅ CloudFront Disabled 완료 (${WAIT_COUNT}초 소요)"
            break
        fi
    done
    
    if [ "$CURRENT_ENABLED" != "False" ]; then
        echo "   ⚠️  타임아웃: CloudFront가 아직 Disabled 상태가 아닙니다."
        echo "   수동으로 확인 후 다시 실행하세요."
        exit 1
    fi
    
    echo ""
else
    echo "2️⃣ CloudFront가 이미 Disabled 상태입니다."
    echo ""
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3단계: CloudFront 삭제
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "4️⃣ CloudFront Distribution 삭제 중..."

# 최신 ETag 가져오기
FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --output json)
FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag')

aws cloudfront delete-distribution \
    --id "$DIST_ID" \
    --if-match "$FINAL_ETAG" \
    >/dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "   ✅ CloudFront 삭제 요청 성공"
else
    echo "   ⚠️  CloudFront 삭제 실패"
    echo "   Distribution이 아직 배포 중일 수 있습니다. 잠시 후 재시도하세요."
    
    # 상태 확인
    aws cloudfront get-distribution --id "$DIST_ID" \
        --query 'Distribution.Status' \
        --output text 2>/dev/null
    
    exit 1
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4단계: CloudFront 완전 삭제 대기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo ""
echo "5️⃣ CloudFront 완전 삭제 대기 중..."
echo "   (예상 시간: 5분)"

MAX_CF_WAIT=300  # 5분
CF_WAIT_COUNT=0

while [ $CF_WAIT_COUNT -lt $MAX_CF_WAIT ]; do
    if [ $((CF_WAIT_COUNT % 30)) -eq 0 ]; then
        echo "   ⏳ 대기 중... (${CF_WAIT_COUNT}초 경과)"
    fi
    
    sleep 10
    CF_WAIT_COUNT=$((CF_WAIT_COUNT + 10))
done

echo "   ✅ CloudFront 완전 삭제 대기 완료"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5단계: ACM Certificate 삭제
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo ""
echo "6️⃣ ACM Certificate 삭제 중..."

# Certificate 사용 여부 확인
CERT_IN_USE=$(aws acm describe-certificate \
    --certificate-arn "$CERT_ARN" \
    --region us-east-1 \
    --query 'Certificate.InUseBy' \
    --output json 2>/dev/null || echo "[]")

IN_USE_COUNT=$(echo "$CERT_IN_USE" | jq '. | length' 2>/dev/null || echo "0")

if [ "$IN_USE_COUNT" -gt 0 ]; then
    echo "   ⚠️  Certificate가 아직 사용 중입니다:"
    echo "$CERT_IN_USE" | jq -r '.[]' 2>/dev/null | while read -r resource; do
        echo "      - $resource"
    done
    echo ""
    echo "   추가 대기 시간이 필요할 수 있습니다. 계속하시겠습니까? (yes/no)"
    read -p "   " CONTINUE
    
    if [ "$CONTINUE" != "yes" ]; then
        echo "   ℹ️  Certificate 삭제를 건너뜁니다."
        echo ""
        echo "   수동 삭제 명령어:"
        echo "   aws acm delete-certificate --certificate-arn \"$CERT_ARN\" --region us-east-1"
        exit 0
    fi
fi

aws acm delete-certificate \
    --certificate-arn "$CERT_ARN" \
    --region us-east-1 \
    >/dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "   ✅ ACM Certificate 삭제 성공"
else
    echo "   ⚠️  ACM Certificate 삭제 실패"
    echo ""
    echo "   상태 확인:"
    aws acm describe-certificate \
        --certificate-arn "$CERT_ARN" \
        --region us-east-1 \
        --query 'Certificate.{InUseBy:InUseBy,Status:Status}' \
        --output json 2>/dev/null || echo "   Certificate를 찾을 수 없습니다 (이미 삭제됨?)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 처리 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 요약:"
echo "   - CloudFront Distribution: 삭제됨"
echo "   - ACM Certificate: 삭제 시도됨"
echo ""

