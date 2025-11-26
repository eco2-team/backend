# CloudFront CDN 활성화/비활성화 가이드

## 🎯 **개요**

CloudFront 생성/삭제는 각각 **10-15분**이 소요되어 배포 시간의 주요 병목입니다.
개발 환경에서는 CloudFront를 비활성화하여 **배포 시간을 85% 단축**할 수 있습니다.

---

## ⏱️ **배포 시간 비교**

### CloudFront 활성화 (기본값: `enable_cloudfront = true`)

```yaml
배포 시간:
  - Terraform apply: 5-7분
  - Ansible bootstrap: 12-15분
  - 총 소요 시간: 20-25분 ⚡

삭제 시간:
  - Terraform destroy: 3-5분
  - 총 소요 시간: 3-5분 ⚡

이미지 전송:
  - S3 Direct URL 사용
  - CORS 설정 필요
  - 속도: 보통 (CDN 없음)
```

### CloudFront 비활성화 (`enable_cloudfront = false`)

```yaml
배포 시간:
  - Terraform apply: 35-40분 (CloudFront 15-20분 포함)
  - Ansible bootstrap: 12-15분
  - 총 소요 시간: 50-60분 🐌

삭제 시간:
  - Terraform destroy: 15-20분 (CloudFront 10-15분 포함)
  - 총 소요 시간: 15-20분 🐌

이미지 전송:
  - CloudFront CDN 사용
  - Global Edge 캐싱
  - 속도: 빠름 (CDN 활용)
```

---

## 🚀 **사용법**

### Option 1: Terraform 변수로 설정 (권장)

`terraform.tfvars` 파일 생성:

```hcl
# terraform/terraform.tfvars
enable_cloudfront = true   # CloudFront 활성화 (기본)
# enable_cloudfront = false # 개발 환경에서 배포 속도가 더 중요할 때
```

### Option 2: 커맨드 라인에서 설정

```bash
# CloudFront 활성화 (기본)
terraform apply -var="enable_cloudfront=true"

# CloudFront 비활성화 (임시 조정)
terraform apply -var="enable_cloudfront=false"
```

### Option 3: `variables.tf`에서 기본값 변경 (이미 true)

필요 시 다른 기본값을 사용하려면 직접 수정을 고려하세요.

---

## 📊 **환경별 권장 설정**

### 개발 환경 (Development)

```hcl
enable_cloudfront = true

이유:
  ✅ CDN URL을 개발·테스트에서도 동일하게 사용
  ✅ 이미지 경로/SSM 값 일관성
  ⚠️ 배포 시간이 늘어나면 일시적으로 `false`로 조정
```

### 스테이징 환경 (Staging)

```hcl
enable_cloudfront = true  # 또는 false (속도 필요 시)

이유:
  - 프로덕션 유사 환경 테스트 필요 시: true
  - 빠른 테스트 반복 필요 시: false
```

### 프로덕션 환경 (Production)

```hcl
enable_cloudfront = true

이유:
  ✅ 이미지 전송 속도 향상
  ✅ Global Edge 캐싱
  ✅ S3 대역폭 비용 절감
  ✅ 사용자 경험 개선
```

---

## 🔧 **현재 배포에 적용하기**

### 1. 진행 중인 배포 중단

```bash
# 현재 배포가 CloudFront 생성 대기 중이라면:
# Ctrl+C로 중단 (안전함 - CloudFront는 백그라운드에서 계속 생성됨)
```

### 2. 기존 리소스 삭제

```bash
cd /Users/mango/workspace/SeSACTHON/backend/scripts/cluster
AUTO_MODE=true ./destroy.sh
```

### 3. CloudFront 비활성화 설정

```bash
cd /Users/mango/workspace/SeSACTHON/backend/terraform

# terraform.tfvars 생성
cat > terraform.tfvars <<EOF
enable_cloudfront = false
EOF
```

### 4. 재배포

```bash
cd /Users/mango/workspace/SeSACTHON/backend/scripts/cluster
./deploy.sh
```

---

## 📝 **CloudFront 비활성화 시 고려사항**

### S3 Direct Access 설정

CloudFront를 사용하지 않으면 S3 Bucket에 직접 접근해야 합니다:

```yaml
필요한 설정:
  1. S3 Bucket Public Access 허용
     - Block public access: OFF

  2. S3 Bucket Policy 추가
     - Principal: "*"
     - Action: "s3:GetObject"

  3. S3 CORS 설정
     - AllowedOrigins: ["*"]
     - AllowedMethods: ["GET", "HEAD"]

주의사항:
  ⚠️  S3 직접 접근 시 대역폭 비용 증가
  ⚠️  CloudFront보다 전송 속도 느림
  ⚠️  Global 사용자 대응 어려움
```

### API 코드 수정

```python
# CloudFront 활성화 시
image_url = f"https://images.growbin.app/{key}"

# CloudFront 비활성화 시
image_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"
# 또는 S3 Presigned URL 사용
```

---

## 🎯 **권장 워크플로우**

```yaml
개발 단계:
  1. 초기 개발: enable_cloudfront = false
     → 빠른 인프라 테스트

  2. 기능 개발: enable_cloudfront = false
     → API 로직 개발 및 테스트

  3. 통합 테스트: enable_cloudfront = false
     → 빠른 반복 테스트

프로덕션 준비:
  4. 성능 테스트: enable_cloudfront = true
     → CloudFront 성능 확인

  5. 프로덕션 배포: enable_cloudfront = true
     → 실제 서비스 운영

프로덕션 운영:
  - CloudFront 유지: enable_cloudfront = true
  - 인프라 변경 시: 별도 Terraform 모듈로 분리 고려
```

---

## 📊 **비용 비교**

### CloudFront 활성화

```yaml
월 예상 비용:
  - CloudFront 데이터 전송: $0.085/GB (첫 10TB)
  - CloudFront HTTP 요청: $0.0075/10,000 요청
  - S3 스토리지: $0.023/GB

예시 (100GB 전송, 1M 요청):
  - CloudFront: $8.50
  - S3 요청: $0.75
  - 총: ~$10/월
```

### CloudFront 비활성화

```yaml
월 예상 비용:
  - S3 데이터 전송: $0.126/GB (첫 10TB)
  - S3 GET 요청: $0.0004/1,000 요청
  - S3 스토리지: $0.023/GB

예시 (100GB 전송, 1M 요청):
  - S3 전송: $12.60
  - S3 요청: $0.40
  - 총: ~$13/월

차이: $3/월 (약 23% 증가)
```

---

## ✅ **결론**

```yaml
개발 환경 (현재):
  권장: enable_cloudfront = false
  이유: 배포 시간 85% 단축 (40분 → 7분)

프로덕션 환경:
  권장: enable_cloudfront = true
  이유: 사용자 경험 향상, 비용 절감
```

---

**Last Updated**: 2025-11-09
**Version**: 1.0
**Status**: ✅ Ready to use
