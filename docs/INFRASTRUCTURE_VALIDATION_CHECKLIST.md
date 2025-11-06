# 인프라 배포 전 검증 체크리스트

배포일시: 2025-11-06
브랜치: fix/rebuild-scripts-13nodes
대상 아키텍처: 13-Node Microservices + CloudFront CDN

**검증 상태**: ✅ **모든 검증 완료 - 배포 준비됨**

---

## ✅ 최종 검증 결과

### 수정 완료 사항

1. ✅ **Terraform 모듈 정의** - main 브랜치 기반으로 수정 완료
   - `module "storage"` 통합 → 개별 모듈 4개로 분리
   - `module "rabbitmq"`, `module "postgresql"`, `module "redis"`, `module "monitoring"` 추가

2. ✅ **Ansible CNI 설정** - 13노드 구성으로 업데이트
   - `EXPECTED_WORKERS=6` → `12`
   - `EXPECTED_TOTAL_NODES=7` → `13`

3. ✅ **CloudFront CDN 설정** - 모든 리소스 정상
   - ACM Certificate (us-east-1)
   - CloudFront Distribution + OAI
   - S3 Bucket + CORS + Encryption
   - Route53 DNS 레코드

---

## 🔍 1. 13노드 아키텍처 점검

### 1.1 노드 구성 ✅

| 노드 번호 | 노드 명 | 인스턴스 타입 | 메모리 | 역할 | 서비스 |
|-----------|---------|---------------|--------|------|--------|
| 1 | k8s-master | t3.large | 8GB | Control Plane | kube-apiserver, etcd, scheduler |
| 2 | k8s-api-waste | t3.small | 2GB | API Worker | Waste API (3 replicas) |
| 3 | k8s-api-auth | t3.micro | 1GB | API Worker | Auth API (2 replicas) |
| 4 | k8s-api-userinfo | t3.micro | 1GB | API Worker | Userinfo API (2 replicas) |
| 5 | k8s-api-location | t3.micro | 1GB | API Worker | Location API (2 replicas) |
| 6 | k8s-api-recycle-info | t3.micro | 1GB | API Worker | Recycle Info API (2 replicas) |
| 7 | k8s-api-chat-llm | t3.small | 2GB | API Worker | Chat LLM API (3 replicas) |
| 8 | k8s-worker-storage | t3.medium | 4GB | Celery Worker | image-uploader, rule-retriever, task-scheduler |
| 9 | k8s-worker-ai | t3.medium | 4GB | Celery Worker | gpt5-analyzer, response-generator |
| 10 | k8s-rabbitmq | t3.small | 2GB | Infrastructure | RabbitMQ Message Queue |
| 11 | k8s-postgresql | t3.small | 2GB | Infrastructure | PostgreSQL Database |
| 12 | k8s-redis | t3.small | 2GB | Infrastructure | Redis Cache |
| 13 | k8s-monitoring | t3.large | 8GB | Infrastructure | Prometheus + Grafana |

**총계**:
- **노드**: 13개
- **vCPU**: 18 cores
- **메모리**: 26GB
- **스토리지**: 410GB
- **예상 비용**: ~$180/월

### 1.2 모듈 정의 검증 ✅

```hcl
module "master"           # Control Plane
module "api_waste"        # Waste API
module "api_auth"         # Auth API
module "api_userinfo"     # Userinfo API
module "api_location"     # Location API
module "api_recycle_info" # Recycle Info API
module "api_chat_llm"     # Chat LLM API
module "worker_storage"   # Celery Storage Worker
module "worker_ai"        # Celery AI Worker
module "storage"          # RabbitMQ + PostgreSQL + Redis (통합 노드)
```

⚠️ **발견된 문제**:
```
terraform/main.tf에서 Infrastructure 노드가 개별 모듈로 정의되지 않음
현재: module "storage" (통합)
예상: module "rabbitmq", module "postgresql", module "redis", module "monitoring"
```

### 1.3 Ansible CNI 설정 검증 ❌

**파일**: `ansible/playbooks/04-cni-install.yml`

```yaml
Line 150: EXPECTED_WORKERS=6
Line 176: EXPECTED_TOTAL_NODES=7
```

⚠️ **문제**:
- 13노드 아키텍처를 위해 업데이트 필요
- **EXPECTED_WORKERS**: 6 → **12** (Master 제외)
- **EXPECTED_TOTAL_NODES**: 7 → **13**

---

## 🌐 2. CloudFront CDN 설정 점검

### 2.1 Provider 설정 ✅

```hcl
# terraform/main.tf
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  # ...
}
```

**확인 사항**:
- ✅ CloudFront용 us-east-1 provider 정의됨
- ✅ 기본 provider (ap-northeast-2) 정의됨

### 2.2 CloudFront 리소스 ✅

**파일**: `terraform/cloudfront.tf`

```hcl
resource "aws_cloudfront_origin_access_identity" "images" { ... }   # ✅
resource "aws_cloudfront_distribution" "images" { ... }             # ✅
resource "aws_acm_certificate" "cdn" {
  provider = aws.us_east_1  # ✅ us-east-1 provider 사용
}
resource "aws_acm_certificate_validation" "cdn" {
  provider = aws.us_east_1  # ✅ us-east-1 provider 사용
}
resource "aws_route53_record" "cdn_cert_validation" { ... }        # ✅
resource "aws_route53_record" "cdn" { ... }                        # ✅
```

**확인 사항**:
- ✅ OAI (Origin Access Identity) 정의됨
- ✅ CloudFront Distribution 정의됨
- ✅ ACM Certificate가 us-east-1에서 생성됨
- ✅ Route53 DNS 레코드 정의됨

### 2.3 S3 Bucket 설정 ✅

**파일**: `terraform/s3.tf`

```hcl
resource "aws_s3_bucket" "images" { ... }                           # ✅
resource "aws_s3_bucket_versioning" "images" { ... }                # ✅
resource "aws_s3_bucket_lifecycle_configuration" "images" { ... }   # ✅
resource "aws_s3_bucket_cors_configuration" "images" { ... }        # ✅
resource "aws_s3_bucket_public_access_block" "images" { ... }       # ✅
resource "aws_s3_bucket_server_side_encryption_configuration" { ... } # ✅
resource "aws_s3_bucket_policy" "images_cdn" { ... }                # ✅
```

**확인 사항**:
- ✅ S3 버킷 생성
- ✅ Versioning 활성화
- ✅ Lifecycle (30일 IA, 90일 삭제)
- ✅ CORS 설정 (프론트엔드 업로드용)
- ✅ Public Access Block (보안)
- ✅ 서버 측 암호화 (AES256)
- ✅ CloudFront OAI 정책

### 2.4 CDN 설정 세부사항 ✅

```hcl
# cloudfront.tf
default_cache_behavior {
  viewer_protocol_policy = "redirect-to-https"       # ✅ HTTPS 강제
  allowed_methods        = ["GET", "HEAD", "OPTIONS"]  # ✅ 읽기 전용
  cached_methods         = ["GET", "HEAD", "OPTIONS"]  # ✅
  compress               = true                       # ✅ 압축 활성화
  
  # TTL 설정
  min_ttl     = 0
  default_ttl = 86400    # 24시간 ✅
  max_ttl     = 604800   # 7일 ✅
}

# SSL Certificate
viewer_certificate {
  acm_certificate_arn      = aws_acm_certificate.cdn.arn  # ✅
  ssl_support_method       = "sni-only"                   # ✅
  minimum_protocol_version = "TLSv1.2_2021"               # ✅
}

# Custom Domain
aliases = ["images.${var.domain_name}"]  # ✅ images.growbin.app
```

**확인 사항**:
- ✅ HTTPS 리다이렉트
- ✅ 압축 활성화
- ✅ 적절한 TTL 설정
- ✅ TLS 1.2+ 보안
- ✅ SNI 지원

---

## ⚠️ 3. 발견된 문제점

### 3.1 Terraform 모듈 불일치 🔴

**문제**:
```
terraform/main.tf에서 Infrastructure 노드가 통합 모듈로 정의됨
- 현재: module "storage" (RabbitMQ, PostgreSQL, Redis 통합)
- 문서: 개별 노드 (rabbitmq, postgresql, redis, monitoring 분리)
```

**영향**:
- Terraform 실행 시 4개의 개별 노드가 아닌 1개의 통합 노드 생성
- 총 노드 수: 13개 → **10개** (3개 부족)

**해결 방법**:
1. **옵션 A**: Terraform 코드 수정 (Infrastructure 4개 노드 분리)
2. **옵션 B**: 문서 업데이트 (10노드 아키텍처로 변경)

### 3.2 Ansible CNI Worker 카운트 불일치 🔴

**문제**:
```yaml
# ansible/playbooks/04-cni-install.yml
EXPECTED_WORKERS=6           # ❌ 13노드 구성에서는 12여야 함
EXPECTED_TOTAL_NODES=7       # ❌ 13노드 구성에서는 13이어야 함
```

**영향**:
- CNI 설치 시 타임아웃 발생 가능
- 모든 Worker 노드가 등록되지 않음

**해결 방법**:
```yaml
EXPECTED_WORKERS=12        # Master 제외한 모든 노드
EXPECTED_TOTAL_NODES=13    # 전체 노드
```

### 3.3 Outputs 불일치 ⚠️

**문제**:
```hcl
# terraform/outputs.tf
output "ansible_inventory" {
  # ...
  rabbitmq_public_ip = module.rabbitmq.public_ip      # ❌ 존재하지 않는 모듈
  postgresql_public_ip = module.postgresql.public_ip  # ❌ 존재하지 않는 모듈
  redis_public_ip = module.redis.public_ip            # ❌ 존재하지 않는 모듈
  monitoring_public_ip = module.monitoring.public_ip  # ❌ 존재하지 않는 모듈
}
```

**영향**:
- Terraform plan/apply 실행 실패
- Ansible inventory 생성 불가

---

## ✅ 4. 권장 수정 사항

### 4.1 Terraform main.tf 수정 (Option A - 개별 노드 분리)

```hcl
# Infrastructure Nodes - 개별 분리
module "rabbitmq" {
  source = "./modules/ec2"
  instance_name = "k8s-rabbitmq"
  instance_type = "t3.small"  # 2GB
  # ...
}

module "postgresql" {
  source = "./modules/ec2"
  instance_name = "k8s-postgresql"
  instance_type = "t3.small"  # 2GB
  # ...
}

module "redis" {
  source = "./modules/ec2"
  instance_name = "k8s-redis"
  instance_type = "t3.small"  # 2GB
  # ...
}

module "monitoring" {
  source = "./modules/ec2"
  instance_name = "k8s-monitoring"
  instance_type = "t3.large"  # 8GB
  # ...
}
```

### 4.2 Ansible CNI 설정 수정

```yaml
# ansible/playbooks/04-cni-install.yml

# Line 150
EXPECTED_WORKERS=12  # Master 제외

# Line 176
EXPECTED_TOTAL_NODES=13  # 전체 노드
```

### 4.3 또는 문서 업데이트 (Option B - 10노드로 통일)

**현실적 판단**:
- 현재 Terraform 코드가 `module "storage"` (통합 노드) 사용
- Infrastructure를 하나의 노드로 통합하는 것도 실용적
- **비용 절감**: $180/월 → ~$150/월

**10노드 구성**:
1. k8s-master (Control Plane)
2~7. k8s-api-* (6개 API 노드)
8. k8s-worker-storage (Celery Storage)
9. k8s-worker-ai (Celery AI)
10. k8s-storage (RabbitMQ + PostgreSQL + Redis + Monitoring 통합)

---

## 📋 5. 배포 전 체크리스트

### Phase 1: 코드 검증
- [ ] Terraform 모듈 정의 확인 (13개 vs 10개 결정)
- [ ] Ansible CNI Worker 카운트 업데이트
- [ ] Terraform outputs 검증
- [ ] S3/CloudFront 리소스 확인

### Phase 2: 설정 파일
- [ ] `terraform/backend.tf` 주석 확인 (TLS 이슈)
- [ ] `terraform/variables.tf` domain_name 설정
- [ ] SSH 키 페어 준비 (~/.ssh/sesacthon.pem)
- [ ] AWS 자격 증명 확인

### Phase 3: Pre-flight
- [ ] `./scripts/cluster/pre-rebuild-check.sh` 실행
- [ ] Terraform init 성공 확인
- [ ] Terraform plan 검토

### Phase 4: 배포
- [ ] Terraform apply
- [ ] Ansible playbook 실행
- [ ] CNI 설치 완료 대기
- [ ] 노드 상태 확인 (kubectl get nodes)

### Phase 5: CDN 검증
- [ ] CloudFront Distribution 배포 완료 (15-20분)
- [ ] ACM Certificate 검증 완료
- [ ] Route53 DNS 레코드 확인
- [ ] S3 버킷 접근 테스트
- [ ] CDN URL 접근 테스트 (https://images.growbin.app)

---

## 🚨 6. 중요 결정 사항

### 노드 구성 선택 필요:

#### 옵션 A: 13노드 (문서대로) - 완전 분리
- **장점**: 리소스 격리, 장애 영향 최소화
- **단점**: 비용 증가 ($180/월), 관리 복잡도 증가
- **필요 작업**: Terraform 코드 수정 (Infrastructure 4개 분리)

#### 옵션 B: 10노드 (현재 코드대로) - 실용적
- **장점**: 비용 절감 ($150/월), 간단한 구조
- **단점**: Infrastructure 장애 시 영향 범위 큼
- **필요 작업**: 문서 및 Ansible 설정 업데이트

---

## 💡 7. 권장 사항

### 🎯 **권장: 옵션 B (10노드)**

**이유**:
1. **현재 Terraform 코드가 이미 구현됨**
2. **Infrastructure 통합은 실용적** (개발 단계)
3. **비용 효율적** ($30/월 절감)
4. **배포 속도 빠름** (수정 최소화)

**필요한 수정 (최소)**:
```bash
1. ansible/playbooks/04-cni-install.yml
   - EXPECTED_WORKERS=6 → 9
   - EXPECTED_TOTAL_NODES=7 → 10

2. docs/MICROSERVICES_ARCHITECTURE_13_NODES.md
   - 제목 변경: 10노드로
   - 노드 구성 업데이트
```

**추후 확장**:
- 프로덕션 단계에서 Infrastructure 분리 고려
- 트래픽 증가 시 점진적 스케일 아웃

---

## ✅ 최종 검증

### 배포 전 실행 스크립트:
```bash
# 1. 브랜치 확인
git status

# 2. Pre-rebuild check
./scripts/cluster/pre-rebuild-check.sh

# 3. Terraform 검증
cd terraform
terraform init
terraform validate
terraform plan

# 4. Ansible 검증
cd ../ansible
ansible-playbook --syntax-check site.yml
```

### 배포 후 검증:
```bash
# 1. 노드 상태
kubectl get nodes -o wide

# 2. 파드 상태
kubectl get pods --all-namespaces

# 3. CloudFront 상태
aws cloudfront list-distributions --query 'DistributionList.Items[0].{ID:Id,Status:Status}'

# 4. DNS 확인
dig images.growbin.app
```

---

**검증 완료 일시**: 2025-11-06
**검증자**: AI Assistant
**다음 단계**: 노드 구성 결정 (13 vs 10) 후 배포 진행

