#!/bin/bash

set -e

# CloudFront Cache Invalidation Script
# Worker에서 S3 업로드 후 CDN 캐시 무효화

# 설정
DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID}"
AWS_REGION="${AWS_REGION:-ap-northeast-2}"

# 사용법
usage() {
    echo "Usage: $0 [OPTIONS] <path>"
    echo ""
    echo "Options:"
    echo "  -d, --distribution-id ID   CloudFront Distribution ID"
    echo "  -p, --path PATH            Path to invalidate (e.g., /images/*)"
    echo "  -b, --batch                Batch mode (stdin에서 경로 목록 읽기)"
    echo "  -h, --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -p '/images/123.jpg'"
    echo "  $0 -p '/images/*'"
    echo "  echo -e '/images/1.jpg\n/images/2.jpg' | $0 -b"
    exit 1
}

# 인자 파싱
BATCH_MODE=false
PATHS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--distribution-id)
            DISTRIBUTION_ID="$2"
            shift 2
            ;;
        -p|--path)
            PATHS+=("$2")
            shift 2
            ;;
        -b|--batch)
            BATCH_MODE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            PATHS+=("$1")
            shift
            ;;
    esac
done

# Distribution ID 확인
if [[ -z "$DISTRIBUTION_ID" ]]; then
    echo "Error: CloudFront Distribution ID is required"
    echo "Set CLOUDFRONT_DISTRIBUTION_ID environment variable or use -d option"
    exit 1
fi

# Batch Mode: stdin에서 경로 읽기
if [[ "$BATCH_MODE" == true ]]; then
    while IFS= read -r line; do
        PATHS+=("$line")
    done
fi

# 경로 확인
if [[ ${#PATHS[@]} -eq 0 ]]; then
    echo "Error: No paths to invalidate"
    usage
fi

# CloudFront Invalidation 생성
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 CloudFront Cache Invalidation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Distribution ID: $DISTRIBUTION_ID"
echo "Paths to invalidate:"
for path in "${PATHS[@]}"; do
    echo "  - $path"
done
echo ""

# AWS CLI로 Invalidation 생성
CALLER_REFERENCE=$(date +%s)
INVALIDATION_BATCH=$(cat <<EOF
{
    "Paths": {
        "Quantity": ${#PATHS[@]},
        "Items": $(printf '"%s"\n' "${PATHS[@]}" | jq -R . | jq -s .)
    },
    "CallerReference": "$CALLER_REFERENCE"
}
EOF
)

echo "Creating invalidation..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --invalidation-batch "$INVALIDATION_BATCH" \
    --region "$AWS_REGION" \
    --query 'Invalidation.Id' \
    --output text)

if [[ -z "$INVALIDATION_ID" ]]; then
    echo "❌ Failed to create invalidation"
    exit 1
fi

echo "✅ Invalidation created: $INVALIDATION_ID"
echo ""

# Invalidation 상태 확인 (선택적)
if [[ "${WAIT_FOR_COMPLETION:-false}" == "true" ]]; then
    echo "⏳ Waiting for invalidation to complete..."
    
    while true; do
        STATUS=$(aws cloudfront get-invalidation \
            --distribution-id "$DISTRIBUTION_ID" \
            --id "$INVALIDATION_ID" \
            --region "$AWS_REGION" \
            --query 'Invalidation.Status' \
            --output text)
        
        echo "   Status: $STATUS"
        
        if [[ "$STATUS" == "Completed" ]]; then
            echo "✅ Invalidation completed!"
            break
        fi
        
        sleep 5
    done
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Cache Invalidation Request Submitted"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Invalidation ID: $INVALIDATION_ID"
echo ""
echo "Check status:"
echo "  aws cloudfront get-invalidation \\"
echo "    --distribution-id $DISTRIBUTION_ID \\"
echo "    --id $INVALIDATION_ID"
echo ""

