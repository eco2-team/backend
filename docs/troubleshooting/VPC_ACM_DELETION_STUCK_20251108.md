# CloudFront/ACM/VPC 삭제 장애 보고서

## 📋 발생 일시
- **날짜**: 2025-11-08 19:47~20:07 (약 20분)
- **스크립트**: `force-destroy-all.sh`
- **실행 모드**: AUTO_MODE=true

---

## 🔴 주요 증상

### 1. **무한 대기 (Infinite Loop)**
```
module.vpc.aws_vpc.main: Still destroying... [19m40s elapsed]
aws_acm_certificate.cdn: Still destroying... [19m40s elapsed]
```

- VPC: 19분 40초 이상 대기
- ACM Certificate (us-east-1): 19분 40초 이상 대기
- **둘 다 삭제되지 않음**

### 2. **CloudFront 감지 실패**
```bash
# 스크립트 출력
1️⃣ CloudFront Distribution 삭제
✅ CloudFront Distribution 없음

# 그러나 실제 상태 (check-aws-resources.sh)
⚠️  남은 Distribution: 1 개
E1GGDPUBLRQG59 | Deployed | False (비활성화됨)
```

**문제**: 스크립트가 CloudFront Distribution을 감지하지 못함!

### 3. **ACM Certificate 사용 중**
```bash
⚠️  ACM Certificate 발견
도메인: images.growbin.app
ARN: arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f
🗑️  Certificate 삭제 중...
⚠️  삭제 실패 (아직 사용 중)
```

**원인**: CloudFront Distribution이 여전히 Certificate 사용 중

---

## 🔍 VPC 남은 리소스 진단 결과

### VPC 상태 (vpc-02562955fe60907d8)

```
VPC ID: vpc-02562955fe60907d8
CIDR: 10.0.0.0/16
State: available
```

### 남은 리소스 (2025-11-08 20:10 확인)

| 리소스 유형 | 개수 | 상세 |
|------------|------|------|
| **VPC** | ✅ 1개 | vpc-02562955fe60907d8 (available) |
| **Subnets** | ⚠️ 3개 | subnet-0001dff6a85b397d2 (10.0.1.0/24, ap-northeast-2a)<br>subnet-02fb1873ce3fbbf58 (10.0.3.0/24, ap-northeast-2c)<br>subnet-0a709bb821539c2e3 (10.0.2.0/24, ap-northeast-2b) |
| Security Groups | ✅ 0개 | default만 존재 (정상) |
| Route Tables | ✅ 0개 | Main Route Table만 존재 (정상) |
| Internet Gateway | ✅ 0개 | 없음 |
| NAT Gateway | ✅ 0개 | 없음 |
| ENI | ✅ 0개 | 없음 |
| VPC Endpoints | ✅ 0개 | 없음 |

**결론**: VPC는 **Subnets 3개만 남아있음**. 그러나 이것만으로는 19분 동안 삭제가 안 되는 이유가 되지 않음.

### CloudFront Distribution 상태

```
ID: E1GGDPUBLRQG59
Status: Deployed
Enabled: false (비활성화됨 ✅)
Domain: d3f4l2e8xigfr9.cloudfront.net
Comment: CDN for waste analysis images - prod
Origins: prod-sesacthon-images.s3.ap-northeast-2.amazonaws.com
Aliases: images.growbin.app
```

**핵심 발견**: 
- CloudFront는 **존재함**
- 이미 **비활성화(Enabled: false)** 상태
- **즉시 삭제 가능**
- 하지만 스크립트가 **감지하지 못함**!

### ACM Certificate 사용 현황

```
Certificate ARN: arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f
Domain: images.growbin.app
Status: ISSUED
InUseBy: 1 개 리소스 (CloudFront Distribution E1GGDPUBLRQG59)
```

**결론**: ACM Certificate가 CloudFront에 의해 사용 중

---

## 🔍 근본 원인 분석

### CloudFront 감지 로직 문제

**현재 스크립트 (force-destroy-all.sh)**:
```bash
CF_DIST_IDS=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(to_string(Origins.Items[].DomainName), 'sesacthon') || contains(to_string(Aliases.Items), 'images.')].Id" \
    --output text 2>/dev/null || echo "")
```

**문제점**:
1. `contains()` 함수가 제대로 작동하지 않음
2. `to_string()` 변환 문제
3. 복잡한 중첩 쿼리

### 실제 CloudFront 상태

```bash
# check-aws-resources.sh로 확인된 실제 상태
Distribution ID: E1GGDPUBLRQG59
Status: Deployed
Enabled: False (비활성화 완료)
Domain: d3f4l2e8xigfr9.cloudfront.net
Comment: CDN for waste analysis images - prod
```

**중요**: 이미 비활성화(Disabled)되었으므로 삭제 가능 상태!

---

## 🔧 VPC 삭제 실패 원인

### Terraform이 시도한 동시 삭제
```
aws_cloudfront_origin_access_identity.images: Destroying...
module.vpc.aws_vpc.main: Destroying...
aws_acm_certificate.cdn: Destroying...
```

**문제**: 3개 리소스를 동시에 삭제 시도
- OAI는 즉시 삭제 가능
- VPC와 ACM은 서로 의존성 있음

### VPC 삭제 장애 원인

1. **CloudFront Distribution 때문에**:
   - CloudFront가 VPC 내 S3 Bucket Policy 참조
   - OAI (Origin Access Identity)가 남아있음

2. **ACM Certificate 때문에**:
   - CloudFront가 Certificate 사용 중
   - Certificate 삭제 불가능

3. **순환 의존성**:
   ```
   CloudFront → ACM Certificate
   CloudFront → S3 Bucket (VPC 내)
   VPC → 모든 리소스 삭제 필요
   ```

---

## 🎯 해결 방법

### 1. CloudFront Distribution 수동 삭제

```bash
# Distribution ID 확인
DIST_ID="E1GGDPUBLRQG59"

# 1. 현재 상태 확인
aws cloudfront get-distribution --id $DIST_ID

# 2. 이미 Disabled 상태이므로 바로 삭제
ETAG=$(aws cloudfront get-distribution-config --id $DIST_ID --output json | jq -r '.ETag')

aws cloudfront delete-distribution --id $DIST_ID --if-match $ETAG
```

**예상 시간**: 5-15분 (Edge Location 캐시 제거)

### 2. ACM Certificate 삭제

CloudFront 삭제 후:
```bash
CERT_ARN="arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f"

aws acm delete-certificate --certificate-arn $CERT_ARN --region us-east-1
```

### 3. VPC 삭제

ACM Certificate 삭제 후:
```bash
VPC_ID="vpc-02562955fe60907d8"

aws ec2 delete-vpc --vpc-id $VPC_ID --region ap-northeast-2
```

### 4. Terraform Destroy 재실행

```bash
cd terraform
terraform destroy -auto-approve
```

---

## 📊 타임라인

| 시각 | 이벤트 | 소요 시간 |
|------|--------|-----------|
| 19:47 | 스크립트 시작 | - |
| 19:47 | CloudFront 감지 실패 | 0초 |
| 19:48 | ACM 대기 시작 (5분 타임아웃) | 5분 |
| 19:53 | ACM 타임아웃 | - |
| 19:53 | Terraform destroy 시작 | - |
| 19:53~20:07 | VPC/ACM 무한 대기 | 14분 |
| 20:07 | 사용자 취소 | - |
| **총 소요 시간** | **약 20분** | **결과: 실패** |

---

## 🐛 스크립트 버그

### 버그 #1: CloudFront 감지 실패

**위치**: `force-destroy-all.sh` Line 145-149

**현재 코드**:
```bash
CF_DIST_IDS=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(to_string(Origins.Items[].DomainName), 'sesacthon') || contains(to_string(Aliases.Items), 'images.')].Id" \
    --output text 2>/dev/null || echo "")
```

**문제**: 복잡한 JMESPath 쿼리가 작동하지 않음

**수정 필요**: 간단한 쿼리로 변경
```bash
CF_DIST_IDS=$(aws cloudfront list-distributions \
    --output json 2>/dev/null | \
    jq -r '.DistributionList.Items[]? | .Id' || echo "")
```

### 버그 #2: ACM 대기 로직

**위치**: `force-destroy-all.sh` Line 206-264

**문제**: 
- CloudFront가 없다고 판단하고도 ACM 대기
- 5분 타임아웃 후에도 계속 진행
- ACM Certificate가 사용 중인지 확인 안 함

**수정 필요**: CloudFront 삭제 전에 ACM 대기하지 말 것

---

## 💡 개선 사항

### 1. CloudFront 감지 개선

```bash
# 모든 Distribution 조회 후 필터링
aws cloudfront list-distributions --output json | \
    jq -r '.DistributionList.Items[]? | 
    select(.Comment | contains("sesacthon") or contains("waste") or contains("images")) | 
    .Id'
```

### 2. 삭제 전 의존성 확인

```bash
# ACM Certificate 사용 현황 확인
IN_USE=$(aws acm describe-certificate \
    --certificate-arn $CERT_ARN \
    --region us-east-1 \
    --query 'Certificate.InUseBy | length(@)' \
    --output text)

if [ "$IN_USE" -gt 0 ]; then
    echo "⚠️  Certificate가 아직 사용 중입니다!"
    # 사용하는 리소스 출력
    aws acm describe-certificate \
        --certificate-arn $CERT_ARN \
        --region us-east-1 \
        --query 'Certificate.InUseBy[]'
fi
```

### 3. 단계별 확인

각 단계 후 실제 삭제 여부 확인:
```bash
# CloudFront 삭제 후
while true; do
    STATUS=$(aws cloudfront get-distribution --id $DIST_ID 2>&1)
    if echo "$STATUS" | grep -q "NoSuchDistribution"; then
        echo "✅ CloudFront 완전 삭제됨"
        break
    fi
    sleep 10
done
```

---

## 📝 권장 조치

### 즉시 조치 (수동)

1. **CloudFront Distribution 삭제**
   ```bash
   ./scripts/utilities/manual-cleanup-cloudfront-acm.sh
   ```

2. **상태 재확인**
   ```bash
   ./scripts/diagnostics/check-aws-resources.sh
   ```

3. **Terraform Destroy 재실행**
   ```bash
   cd terraform && terraform destroy -auto-approve
   ```

### 장기 조치 (스크립트 개선)

1. CloudFront 감지 로직 수정
2. 의존성 확인 로직 추가
3. 단계별 검증 강화
4. 타임아웃 처리 개선

---

## 🔗 관련 문서

- `docs/troubleshooting/CLOUDFRONT_ACM_CERTIFICATE_STUCK.md`
- `scripts/utilities/manual-cleanup-cloudfront-acm.sh`
- `scripts/diagnostics/check-aws-resources.sh`

---

**작성 일시**: 2025-11-08 20:10
**작성자**: AI Assistant
**상태**: 진행 중 (수동 삭제 필요)

