# CloudFront 검색 로직 부족으로 인한 ACM Certificate 삭제 실패

> 날짜: 2025-11-08  
> 심각도: 🔴 High (리소스 삭제 실패)

---

## 📌 문제 요약

**증상**:
- ACM Certificate 삭제 시 10분 이상 대기 후 타임아웃
- CloudFront Distribution이 Certificate를 사용 중이라는 에러
- 하지만 `destroy-with-cleanup.sh`에서 CloudFront를 검색하지 못함

**원인**:
- CloudFront 검색 쿼리가 S3 버킷 이름만 검색
- ACM Certificate를 사용하는 다른 Origin의 Distribution은 검색 안 됨

**영향**:
- 인프라 삭제 실패
- CloudFront와 ACM Certificate가 계속 비용 발생
- 수동 개입 필요

---

## 🔍 문제 발견 과정

### 1. ACM Certificate 삭제 시 대기 발생

```bash
🔐 ACM Certificate 정리 (us-east-1)...
⚠️  ACM Certificate 발견:
  - 도메인: images.growbin.app
    ARN: arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f
    ⚠️  Certificate가 아직 사용 중입니다:
       - arn:aws:cloudfront::721622471953:distribution/E1GGDPUBLRQG59
    ⏳ CloudFront 완전 삭제 대기 중 (최대 10분)...
       ⏳ 대기 중... (0초 경과)
       ⏳ 대기 중... (30초 경과)
       ⏳ 대기 중... (60초 경과)
       ⏳ 대기 중... (90초 경과)
       ⏳ 대기 중... (120초 경과)
       ... (계속 대기)
```

### 2. CloudFront Distribution 상태 확인

```bash
$ aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.{Status:Status,Enabled:DistributionConfig.Enabled,DomainName:DomainName}' \
    --output json
```

**결과**:
```json
{
    "Status": "Deployed",
    "Enabled": true,  // ⚠️ 여전히 활성화 상태!
    "DomainName": "d3f4l2e8xigfr9.cloudfront.net"
}
```

### 3. 근본 원인 분석

**`destroy-with-cleanup.sh` 430줄 검색 쿼리**:
```bash
# 문제가 있는 검색 쿼리
CF_DISTRIBUTIONS=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(Origins.Items[].DomainName, 'sesacthon-images')].Id" \
    --output text 2>/dev/null || echo "")
```

**문제점**:
1. S3 버킷 이름(`sesacthon-images`)만 검색
2. ACM Certificate를 사용하는 Distribution은 검색하지 않음
3. Aliases(CNAME)를 사용하는 Distribution도 검색하지 않음

**결과**:
- Distribution `E1GGDPUBLRQG59`가 검색되지 않음
- CloudFront가 Enabled 상태로 남아있음
- ACM Certificate 삭제 불가 (CloudFront가 사용 중)

---

## 🛠️ 해결 방법

### 방법 1: 스크립트 개선 (권장)

**`destroy-with-cleanup.sh` 개선**:

```bash
# 5-1. CloudFront Distribution 확인 및 삭제
echo "🌐 CloudFront Distribution 확인..."

# 1. S3 버킷 기반 검색
CF_DISTRIBUTIONS_S3=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(Origins.Items[].DomainName, 'sesacthon-images')].Id" \
    --output text 2>/dev/null || echo "")

# 2. ACM Certificate 기반 검색 (images. 도메인) ← 새로 추가!
CF_DISTRIBUTIONS_ACM=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(to_string(ViewerCertificate.ACMCertificateArn), 'images') || contains(to_string(Aliases.Items), 'images')].Id" \
    --output text 2>/dev/null || echo "")

# 3. 중복 제거하고 병합
CF_DISTRIBUTIONS=$(echo "$CF_DISTRIBUTIONS_S3 $CF_DISTRIBUTIONS_ACM" | tr ' ' '\n' | sort -u | tr '\n' ' ')

if [ -n "$CF_DISTRIBUTIONS" ]; then
    echo "⚠️  CloudFront Distribution 발견 (삭제 시 5-10분 소요):"
    for dist_id in $CF_DISTRIBUTIONS; do
        echo "  📋 Distribution ID: $dist_id"
        
        # Distribution Config 가져오기
        CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json 2>/dev/null || echo "")
        
        if [ -n "$CONFIG" ] && [ "$CONFIG" != "" ]; then
            ETAG=$(echo "$CONFIG" | jq -r '.ETag' 2>/dev/null || echo "")
            IS_ENABLED=$(echo "$CONFIG" | jq -r '.DistributionConfig.Enabled' 2>/dev/null || echo "true")
            
            if [ "$IS_ENABLED" = "true" ]; then
                echo "  - Disabling Distribution: $dist_id"
                
                # Enabled를 false로 변경
                NEW_CONFIG=$(echo "$CONFIG" | jq '.DistributionConfig | .Enabled = false' 2>/dev/null)
                
                if [ -n "$NEW_CONFIG" ] && [ -n "$ETAG" ]; then
                    aws cloudfront update-distribution \
                        --id "$dist_id" \
                        --if-match "$ETAG" \
                        --distribution-config "$NEW_CONFIG" \
                        >/dev/null 2>&1 || true
                    
                    echo "  ⏳ Distribution Disabled 상태 대기 (2분)..."
                    sleep 120
                fi
            fi
            
            # 삭제
            echo "  - Deleting Distribution: $dist_id"
            FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json 2>/dev/null || echo "")
            FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag' 2>/dev/null || echo "")
            
            if [ -n "$FINAL_ETAG" ]; then
                aws cloudfront delete-distribution --id "$dist_id" --if-match "$FINAL_ETAG" 2>/dev/null || \
                    echo "    ⚠️  삭제 실패 (아직 배포 중이거나 사용 중)"
            fi
        fi
    done
else
    echo "  ✅ CloudFront Distribution 없음"
fi
```

**개선 포인트**:
- ✅ S3 버킷 이름 기반 검색
- ✅ ACM Certificate ARN 기반 검색 (새로 추가)
- ✅ Aliases(CNAME) 기반 검색 (새로 추가)
- ✅ 중복 제거 및 일괄 처리

---

### 방법 2: 수동 해결 (즉시 필요 시)

현재 스크립트를 중단(Ctrl+C)하고 수동으로 처리:

```bash
# 1. CloudFront Distribution 비활성화
DIST_ID="E1GGDPUBLRQG59"  # 실제 Distribution ID 입력

CONFIG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --output json)
ETAG=$(echo "$CONFIG" | jq -r '.ETag')
NEW_CONFIG=$(echo "$CONFIG" | jq '.DistributionConfig | .Enabled = false')

aws cloudfront update-distribution \
    --id "$DIST_ID" \
    --if-match "$ETAG" \
    --distribution-config "$NEW_CONFIG"

echo "✅ CloudFront Disabled 요청 완료"

# 2. Disabled 상태 대기 (2-5분)
echo "⏳ CloudFront Disabled 대기 중..."
sleep 180

# 3. Distribution 상태 확인
aws cloudfront get-distribution --id "$DIST_ID" \
    --query 'Distribution.{Status:Status,Enabled:DistributionConfig.Enabled}' \
    --output json

# 4. CloudFront Distribution 삭제
FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --output json)
FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag')

aws cloudfront delete-distribution \
    --id "$DIST_ID" \
    --if-match "$FINAL_ETAG"

echo "✅ CloudFront 삭제 요청 완료"

# 5. ACM Certificate 삭제 (CloudFront 삭제 완료 후 5분 대기)
echo "⏳ CloudFront 완전 삭제 대기 중..."
sleep 300

# 6. ACM Certificate 삭제
aws acm delete-certificate \
    --certificate-arn "arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f" \
    --region us-east-1

echo "✅ ACM Certificate 삭제 완료"
```

**소요 시간**: 약 8-13분
- CloudFront Disable: 2-5분
- CloudFront 완전 삭제: 5-10분

---

## 🔐 예방 방법

### 1. Terraform에 태그 추가

**`terraform/cloudfront.tf`**:
```hcl
resource "aws_cloudfront_distribution" "images" {
  # ... 기존 설정 ...
  
  tags = {
    Name        = "sesacthon-images-cdn"
    Project     = "SeSACTHON"
    ManagedBy   = "Terraform"
    Environment = var.environment
    # 삭제 스크립트 검색용
    SearchKey   = "sesacthon-cleanup"  # ← 추가
  }
}
```

### 2. 태그 기반 검색 사용

```bash
# 태그 기반 검색 (가장 확실함)
CF_DISTRIBUTIONS_TAG=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Tags.Items[?Key=='SearchKey' && Value=='sesacthon-cleanup']].Id" \
    --output text 2>/dev/null || echo "")
```

**장점**:
- ✅ S3 Origin 변경에 영향 받지 않음
- ✅ ACM Certificate 변경에 영향 받지 않음
- ✅ 명확한 프로젝트 식별

---

## 📊 디버깅 명령어

### 1. 모든 CloudFront Distribution 목록

```bash
aws cloudfront list-distributions \
    --query "DistributionList.Items[*].{Id:Id,DomainName:DomainName,Status:Status,Enabled:DistributionConfig.Enabled}" \
    --output table
```

### 2. ACM Certificate 사용 여부 확인

```bash
aws acm describe-certificate \
    --certificate-arn "arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f" \
    --region us-east-1 \
    --query 'Certificate.{InUseBy:InUseBy,Status:Status}' \
    --output json
```

**출력 예시**:
```json
{
    "InUseBy": [
        "arn:aws:cloudfront::721622471953:distribution/E1GGDPUBLRQG59"
    ],
    "Status": "ISSUED"
}
```

### 3. Distribution의 Origin 확인

```bash
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.DistributionConfig.Origins.Items[*].DomainName' \
    --output json
```

### 4. Distribution의 Certificate 확인

```bash
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.DistributionConfig.ViewerCertificate' \
    --output json
```

**출력 예시**:
```json
{
    "CloudFrontDefaultCertificate": false,
    "ACMCertificateArn": "arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021",
    "Certificate": "arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f",
    "CertificateSource": "acm"
}
```

### 5. Distribution의 Aliases(CNAME) 확인

```bash
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.DistributionConfig.Aliases' \
    --output json
```

---

## 🎯 체크리스트

**문제 진단**:
- [ ] ACM Certificate 삭제 시 10분 이상 대기
- [ ] ACM Certificate가 CloudFront에서 사용 중
- [ ] CloudFront Distribution이 여전히 Enabled: true
- [ ] `destroy-with-cleanup.sh`에서 CloudFront를 찾지 못함

**해결 확인**:
- [ ] CloudFront 검색 로직 개선 적용
- [ ] Distribution이 올바르게 검색됨
- [ ] Distribution이 Disabled 상태로 변경됨
- [ ] Distribution이 성공적으로 삭제됨
- [ ] ACM Certificate가 성공적으로 삭제됨

---

## 💡 교훈

1. **다중 검색 전략 필요**:
   - 단일 조건으로 검색하면 누락 가능
   - S3 Origin, ACM Certificate, Aliases 등 다각도 검색

2. **태그 기반 관리 권장**:
   - 가장 확실한 식별 방법
   - 인프라 변경에 영향 받지 않음

3. **철저한 상태 확인**:
   - 리소스 삭제 전 실제 존재 여부 확인
   - "없음"으로 표시되어도 실제로 존재할 수 있음

---

## 📚 관련 문서

- [CloudFront Developer Guide](https://docs.aws.amazon.com/cloudfront/)
- [ACM Certificate Validation](https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-validate-dns.html)
- [VPC_DELETION_DELAY.md](./VPC_DELETION_DELAY.md)

---

## 🔗 관련 커밋

- `fix: Improve CloudFront detection logic to include ACM Certificate-based search`
- `fix: Add multiple search strategies for CloudFront Distribution cleanup`
- `docs: Add CLOUDFRONT_ACM_CERTIFICATE_STUCK troubleshooting guide`

---

**최종 업데이트**: 2025-11-08  
**상태**: ✅ 해결됨 (스크립트 개선)

