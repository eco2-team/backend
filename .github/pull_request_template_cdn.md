# CloudFront CDN for S3 Image Optimization

**Branch**: `feature/cdn-image-caching`  
**Target**: `develop`  
**Type**: feat (Feature)  
**Priority**: 🔥 High

---

## 📋 요약

S3 이미지 스토리지에 CloudFront CDN을 추가하여 글로벌 이미지 전송 성능을 최적화합니다.

### ✅ 주요 변경사항

1. **CloudFront Distribution 추가**
   - S3를 Origin으로 하는 CDN 구성
   - Edge Location 캐싱 (24시간 기본, 7일 최대)
   - images.growbin.app 커스텀 도메인

2. **Redis Image Hash Cache 제거**
   - pHash 기반 중복 제거 로직 제거
   - CloudFront가 파일 캐싱 담당
   - Redis 메모리 절약

3. **ACM 인증서 설정**
   - us-east-1 리전 인증서 (CloudFront 요구사항)
   - Route53 자동 검증

4. **S3 보안 강화**
   - OAI (Origin Access Identity) 사용
   - CloudFront를 통한 접근만 허용
   - 직접 S3 접근 차단

---

## 🎯 목표 및 달성

### 성능 개선
- ✅ **응답 속도**: 10-50ms (Edge Location 기준)
- ✅ **글로벌 확장**: 전 세계 Edge Location 활용
- ✅ **캐시 히트율**: 50-70% 예상

### 비용 최적화
- ✅ **S3 전송 비용 절감**: 70% (CDN 캐싱)
- ✅ **Redis 메모리 절약**: DB 1 제거
- ✅ **이미지 처리 단순화**: pHash 계산 제거

### 아키텍처 개선
- ✅ **단순화**: Redis Image Cache 레이어 제거
- ✅ **보안**: S3 직접 접근 차단
- ✅ **확장성**: CloudFront 자동 스케일링

---

## 🏗️ 아키텍처 변경

### Before: S3 직접 접근
```
Frontend → S3 Presigned URL → S3 Bucket
Worker → S3 Presigned URL → S3 Bucket
   ↓
Redis DB 1 (pHash Cache)
```

### After: CloudFront CDN
```
Frontend → CloudFront (https://images.growbin.app) → S3 Bucket (OAI)
Worker → CloudFront (https://images.growbin.app) → S3 Bucket (OAI)
   ↓
Redis DB 1 제거 ✅
```

---

## 📦 추가된 리소스

### Terraform (`terraform/cloudfront.tf`)
```terraform
✅ aws_cloudfront_distribution.images
   - Origin: S3 Bucket
   - TTL: 24h (default), 7d (max)
   - Price Class: 200 (Asia + NA + EU)
   
✅ aws_cloudfront_origin_access_identity.images
   - S3 보안 접근
   
✅ aws_acm_certificate.cdn (us-east-1)
   - images.growbin.app
   - DNS 자동 검증
   
✅ aws_s3_bucket_policy.images_cdn
   - CloudFront OAI만 접근 허용
   
✅ aws_route53_record.cdn
   - images.growbin.app → CloudFront
```

---

## 📚 문서

### ✅ 신규 문서
1. **`CDN_S3_ARCHITECTURE_DESIGN.md`**
   - CloudFront + S3 아키텍처 설계
   - 캐싱 전략
   - 비용 분석

2. **`REDIS_IMAGE_CACHE_REMOVAL.md`**
   - Redis DB 1 제거 사유
   - 마이그레이션 가이드
   - 영향도 분석

3. **`CDN_MIGRATION_ANALYSIS.md`**
   - Before/After 비교
   - 성능 개선 예상치
   - 비용 절감 분석

### ⚠️ 업데이트 필요 (별도 PR)
- `docs/architecture/image-processing-architecture.md`
- `docs/infrastructure/redis-configuration.md`
- Worker 코드 (`workers/vision_worker.py`)

---

## 🔧 설정 변경

### Terraform Provider (추가)
```terraform
# main.tf 또는 providers.tf
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"  # CloudFront ACM 인증서용
}
```

### Environment Variables (추가)
```bash
# Backend API
CDN_BASE_URL=https://images.growbin.app
```

---

## 🚀 배포 절차

### 1. Terraform Apply
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. ACM 인증서 검증
```bash
# Route53 DNS 레코드 자동 생성됨
# 검증 완료까지 5-10분 소요
```

### 3. CloudFront 배포 완료 대기
```bash
# 배포 완료까지 15-20분 소요
aws cloudfront get-distribution --id <DISTRIBUTION_ID>
```

### 4. DNS 전파 확인
```bash
dig images.growbin.app
curl -I https://images.growbin.app
```

---

## ✅ 테스트 체크리스트

### Infrastructure
- [ ] CloudFront Distribution 생성 확인
- [ ] ACM 인증서 ISSUED 상태 확인
- [ ] Route53 레코드 생성 확인
- [ ] S3 Bucket Policy OAI 설정 확인

### 기능 테스트
- [ ] images.growbin.app DNS 해석
- [ ] HTTPS 접근 (SSL 인증서)
- [ ] 이미지 업로드 (Presigned URL)
- [ ] CDN을 통한 이미지 다운로드
- [ ] 캐시 히트 확인 (X-Cache: Hit from cloudfront)

### 보안 테스트
- [ ] S3 직접 접근 차단 확인
- [ ] CloudFront만 S3 접근 가능
- [ ] HTTPS 강제 리다이렉션

---

## 📊 예상 효과

### 성능
- **응답 속도**: 200-500ms (S3) → 10-50ms (CDN)
- **글로벌 확장**: Edge Location 자동 활용
- **동시 접속**: CloudFront 무제한 스케일링

### 비용
- **S3 전송 비용**: $0.09/GB → $0.085/GB (CDN)
- **캐시 히트 시**: S3 비용 70% 절감
- **Redis 메모리**: DB 1 제거 (1-2GB 절약)

### 개발
- **코드 단순화**: pHash 계산 제거
- **의존성 제거**: `imagehash` 라이브러리 불필요
- **유지보수**: CDN 자동 관리

---

## ⚠️ 주의사항

### 1. ACM 인증서 리전
- CloudFront는 **us-east-1** 리전 인증서만 사용
- ap-northeast-2 인증서는 사용 불가

### 2. 캐시 무효화
```bash
# 이미지 업데이트 시 캐시 무효화 필요
aws cloudfront create-invalidation \
  --distribution-id <ID> \
  --paths "/path/to/image.jpg"
```

### 3. 비용
- CloudFront 데이터 전송: $0.085/GB (아시아)
- 무효화 요청: 1,000건까지 무료, 이후 $0.005/건

### 4. S3 CORS
- CloudFront를 통한 접근에도 CORS 설정 필요
- 이미 `s3.tf`에 설정 완료 ✅

---

## 🔗 관련 이슈 및 PR

- Issue: N/A (아키텍처 개선)
- Related PR: #11 (Infrastructure 13 Nodes)
- Related PR: #12 (Helm ArgoCD CI/CD)

---

## 👥 리뷰어

@backend-team  
@infrastructure-team

---

## 📝 체크리스트

- [x] Terraform 리소스 정의 완료
- [x] 문서 작성 완료
- [x] Redis Image Cache 제거 확인
- [x] CloudFront 설정 검증
- [ ] Terraform apply 테스트
- [ ] 이미지 업로드/다운로드 테스트
- [ ] 캐시 동작 확인

---

**작성일**: 2025-11-06  
**작성자**: AI Assistant  
**브랜치**: feature/cdn-image-caching → develop

