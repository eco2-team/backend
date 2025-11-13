#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AWS Credentials Secret 생성 스크립트
# Worker Pod가 S3 접근 시 사용
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 AWS Credentials Secret 생성"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 환경변수 확인
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo "❌ AWS_ACCESS_KEY_ID 환경변수가 설정되지 않았습니다."
    echo ""
    echo "사용법:"
    echo "  export AWS_ACCESS_KEY_ID='your-access-key'"
    echo "  export AWS_SECRET_ACCESS_KEY='your-secret-key'"
    echo "  ./scripts/create-aws-credentials-secret.sh"
    exit 1
fi

if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "❌ AWS_SECRET_ACCESS_KEY 환경변수가 설정되지 않았습니다."
    exit 1
fi

# 네임스페이스 목록
NAMESPACES=(
    "workers"        # Worker Pods
    "data"           # PostgreSQL, Redis (백업 시 S3 사용 가능)
    "scan"           # Scan API (S3 이미지 업로드)
)

echo ""
echo "✅ AWS Credentials 확인 완료"
echo "  Access Key ID: ${AWS_ACCESS_KEY_ID:0:10}..."
echo ""

# 각 네임스페이스에 Secret 생성
for NS in "${NAMESPACES[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 네임스페이스: $NS"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 네임스페이스 존재 확인
    if ! kubectl get namespace $NS &>/dev/null; then
        echo "⚠️  네임스페이스 '$NS'가 존재하지 않습니다. 생성합니다..."
        kubectl create namespace $NS
    fi
    
    # Secret 존재 확인
    if kubectl get secret aws-credentials -n $NS &>/dev/null; then
        echo "⚠️  Secret 'aws-credentials'가 이미 존재합니다. 업데이트합니다..."
        kubectl delete secret aws-credentials -n $NS
    fi
    
    # Secret 생성
    kubectl create secret generic aws-credentials \
        -n $NS \
        --from-literal=access-key-id="$AWS_ACCESS_KEY_ID" \
        --from-literal=secret-access-key="$AWS_SECRET_ACCESS_KEY" \
        --from-literal=region="${AWS_REGION:-ap-northeast-2}"
    
    echo "✅ Secret 'aws-credentials' 생성 완료 ($NS)"
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 모든 AWS Credentials Secret 생성 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 검증
echo ""
echo "📊 생성된 Secret 확인:"
for NS in "${NAMESPACES[@]}"; do
    echo "  - $NS: $(kubectl get secret aws-credentials -n $NS -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null || echo 'Not found')"
done

echo ""
echo "💡 Pod에서 사용 예시:"
echo ""
echo "  env:"
echo "    - name: AWS_ACCESS_KEY_ID"
echo "      valueFrom:"
echo "        secretKeyRef:"
echo "          name: aws-credentials"
echo "          key: access-key-id"
echo "    - name: AWS_SECRET_ACCESS_KEY"
echo "      valueFrom:"
echo "        secretKeyRef:"
echo "          name: aws-credentials"
echo "          key: secret-access-key"
echo "    - name: AWS_REGION"
echo "      valueFrom:"
echo "        secretKeyRef:"
echo "          name: aws-credentials"
echo "          key: region"
echo ""

