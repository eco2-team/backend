# Troubleshooting Guide - 이코에코(Eco²)

> 14-Node Microservices Architecture + Worker Local SQLite WAL 구축 과정에서 발생한 문제 및 해결 방안

## 📋 목차

- [1. Terraform 관련 문제](#1-terraform-관련-문제)
- [2. IAM Policy 중복 문제](#2-iam-policy-중복-문제)
- [3. AWS 한도 관련 문제](#3-aws-한도-관련-문제)
- [4. 스크립트 실행 문제](#4-스크립트-실행-문제)
- [5. GitHub CLI 인증 문제](#5-github-cli-인증-문제)
- [6. CloudFront 관련 문제](#6-cloudfront-관련-문제)
- [7. VPC 삭제 지연 문제](#7-vpc-삭제-지연-문제)
- [8. ArgoCD 리디렉션 루프 문제](#8-argocd-리디렉션-루프-문제)
- [9. Prometheus 메모리 부족 문제](#9-prometheus-메모리-부족-문제)
- [10. Atlantis Pod CrashLoopBackOff 문제](#10-atlantis-pod-crashloopbackoff-문제)
- [11. 베스트 프랙티스](#11-베스트-프랙티스)
- [12. 참고 문서](#12-참고-문서)
- [13. 지원](#13-지원)

---

## 1. Terraform 관련 문제

### 1.1. Duplicate Resource Configuration

#### 문제
```
Error: Duplicate resource "aws_iam_policy" configuration
Error: Duplicate resource "aws_iam_role_policy_attachment" configuration
```

**원인**: 동일한 리소스가 여러 파일에 선언됨
- `terraform/iam.tf`와 `terraform/alb-controller-iam.tf`에 `aws_iam_policy.alb_controller` 중복

#### 해결
```bash
# iam.tf에서 중복 선언 제거
# alb-controller-iam.tf에만 유지
```

**적용 파일**:
- `terraform/iam.tf` (중복 제거)
- `terraform/alb-controller-iam.tf` (유지)

**커밋**: `feat: Remove duplicate IAM policy declarations`

---

### 1.2. Provider Configuration Not Present

#### 문제
```
Error: Provider configuration not present
To work with aws_acm_certificate.cdn its original provider configuration at 
provider["registry.terraform.io/hashicorp/aws"].us_east_1 is required
```

**원인**: CloudFront ACM 인증서는 `us-east-1` 리전에 있어야 하지만 provider 설정 누락

#### 해결
`terraform/main.tf`에 `us-east-1` provider 추가:

```hcl
# CloudFront requires ACM certificate in us-east-1
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  
  default_tags {
    tags = {
      Project     = "SeSACTHON"
      ManagedBy   = "Terraform"
      Environment = var.environment
      Team        = "Backend"
    }
  }
}
```

**커밋**: `fix: Add us-east-1 provider for CloudFront ACM certificates`

---

### 1.3. Reference to Undeclared Resource

#### 문제
```
Error: Reference to undeclared resource
A managed resource "aws_iam_role" "ec2_ssm_role" has not been declared
```

**원인**: 잘못된 IAM role 참조
- `alb-controller-iam.tf`와 `s3.tf`에서 `aws_iam_role.ec2_ssm_role` 참조
- 실제 리소스 이름은 `aws_iam_role.k8s_node`

#### 해결
```hcl
# Before
role = aws_iam_role.ec2_ssm_role.name

# After
role = aws_iam_role.k8s_node.name
```

**적용 파일**:
- `terraform/alb-controller-iam.tf`
- `terraform/s3.tf`

**커밋**: `fix: Correct IAM role reference from ec2_ssm_role to k8s_node`

---

### 1.4. Missing Resource Instance Key

#### 문제
```
Error: Missing resource instance key
Because data.aws_route53_zone.main has "count" set, its attributes must be 
accessed on specific instances.
```

**원인**: `count` 기반 리소스를 인덱스 없이 참조

#### 해결
```hcl
# Before
zone_id = data.aws_route53_zone.main.zone_id

# After
zone_id = data.aws_route53_zone.main[0].zone_id
```

**적용 파일**: `terraform/cloudfront.tf`

**커밋**: `fix: Add index to count-based Route53 zone reference`

---

### 1.5. Invalid Attribute Combination (S3 Lifecycle)

#### 문제
```
Warning: Invalid Attribute Combination
No attribute specified when one (and only one) of [rule[0].filter,rule[0].prefix] is required
```

**원인**: S3 lifecycle rule에 `filter` 또는 `prefix` 필수

#### 해결
```hcl
resource "aws_s3_bucket_lifecycle_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    id     = "cleanup-old-images"
    status = "Enabled"

    filter {
      prefix = ""  # 모든 객체에 적용
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 90
    }
  }
}
```

**적용 파일**: `terraform/s3.tf`

**커밋**: `fix: Add filter block to S3 lifecycle configuration`

---

### 1.6. No Configuration Files

#### 문제
```
Error: No configuration files
Apply requires configuration to be present.
```

**원인**: `auto-rebuild.sh`의 Step 2에서 terraform 디렉토리로 이동하지 않음

#### 해결
```bash
# Step 2 시작 시 명시적으로 디렉토리 이동
cd "$PROJECT_ROOT/terraform"

echo "🔧 Terraform 초기화 (재확인)..."
terraform init -migrate-state -upgrade
```

**적용 파일**: `scripts/cluster/auto-rebuild.sh`

**커밋**: `fix: Add missing cd to terraform directory in auto-rebuild.sh Step 2`

---

## 2. IAM Policy 중복 문제

### 2.1. EntityAlreadyExists - IAM Policy

#### 문제
```
Error: creating IAM Policy (prod-alb-controller-policy): EntityAlreadyExists
Error: creating IAM Policy (prod-s3-presigned-url-policy): EntityAlreadyExists
```

**원인**: 이전 배포의 IAM Policy가 Terraform state에 없지만 AWS에 남아있음

#### 해결
`scripts/maintenance/destroy-with-cleanup.sh`에 IAM Policy 강제 정리 추가:

```bash
# IAM Policy 강제 정리
echo "🔐 IAM Policy 강제 정리..."
POLICY_ARNS=$(aws iam list-policies --scope Local \
    --query "Policies[?contains(PolicyName, 'alb-controller') || contains(PolicyName, 'ecoeco') || contains(PolicyName, 's3-presigned-url')].Arn" \
    --output text)

if [ -n "$POLICY_ARNS" ]; then
    for policy_arn in $POLICY_ARNS; do
        # Role에서 detach
        ATTACHED_ROLES=$(aws iam list-entities-for-policy \
            --policy-arn "$policy_arn" \
            --entity-filter Role \
            --query 'PolicyRoles[*].RoleName' \
            --output text)
        
        for role in $ATTACHED_ROLES; do
            aws iam detach-role-policy --role-name "$role" --policy-arn "$policy_arn"
        done
        
        # Policy 삭제
        aws iam delete-policy --policy-arn "$policy_arn"
    done
fi
```

**커밋**: `feat: Enhance destroy-with-cleanup.sh with comprehensive AWS resource cleanup`

---

### 2.2. auto-rebuild.sh 통합

#### 문제
`auto-rebuild.sh`가 복잡한 정리 로직을 직접 구현하여 유지보수 어려움

#### 해결
`destroy-with-cleanup.sh`를 호출하도록 리팩토링:

```bash
# Step 1: Terraform Destroy (destroy-with-cleanup.sh 호출)
if [ -f "$PROJECT_ROOT/scripts/maintenance/destroy-with-cleanup.sh" ]; then
    echo "🔧 destroy-with-cleanup.sh 실행 중..."
    export AUTO_MODE=true
    bash "$PROJECT_ROOT/scripts/maintenance/destroy-with-cleanup.sh"
else
    # Fallback: 간단한 destroy
    terraform destroy -auto-approve
fi
```

**효과**:
- 200+ 줄 코드 제거
- 단일 정리 로직으로 통합
- IAM, S3, CloudFront, Route53, ACM 모두 자동 정리

**커밋**: `feat: Integrate destroy-with-cleanup.sh into auto-rebuild.sh + S3 Policy cleanup`

---

## 3. AWS 한도 관련 문제

### 3.1. VcpuLimitExceeded

#### 문제
```
Error: creating EC2 Instance: VcpuLimitExceeded
You have requested more vCPU capacity than your current vCPU limit of 16 allows
```

**원인**: 14-Node 아키텍처 필요 vCPU (26) > 계정 한도 (16)

**vCPU 계산**:
| 노드 타입 | 개수 | 인스턴스 | vCPU/노드 | 총 vCPU |
|----------|------|---------|-----------|---------|
| Master | 1 | t3a.large | 2 | 2 |
| API | 6 | t3a.medium | 2 | 12 |
| Worker | 2 | t3a.large | 2 | 4 |
| Infrastructure | 4 | t3a.medium | 2 | 8 |
| **합계** | **13** | | | **26** |

#### 해결 방법 1: vCPU 한도 증가 요청 (권장)

**자동 스크립트**:
```bash
./scripts/utilities/request-vcpu-increase.sh
```

**수동 요청**:
```bash
aws service-quotas request-service-quota-increase \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --desired-value 32 \
    --region ap-northeast-2
```

**AWS Console**: Service Quotas → EC2 → "Running On-Demand Standard instances"

**승인 시간**: 15분-2시간 (일반적)

**한도 확인**:
```bash
aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region ap-northeast-2 \
    --query 'Quota.Value'
```

#### 해결 방법 2: 멀티 리전 배포 (권장)

✅ **성능 유지** - 한도 증가 전까지 임시 운영

**전략**: Stateless 서비스를 도쿄 리전(ap-northeast-1)으로 분산

**필수 API 현황 (7개)**:
1. auth - 인증/인가
2. my - 마이페이지 (userinfo)
3. info - 재활용 정보 (recycle_info)
4. location - 위치/지도
5. character - 캐릭터/미션 (신규 추가 필요)
6. scan - 폐기물 스캔/분석 (waste)
7. chat - 챗봇 (chat_llm)

**서울 리전 (ap-northeast-2) - 14 vCPU**:
```
Master        (t3.large)  = 2 vCPU  ← Kubernetes 컨트롤 플레인
API-Auth      (t3.micro)  = 2 vCPU  ← 인증 (지연 민감)
API-My        (t3.micro)  = 2 vCPU  ← 마이페이지 (DB 직접 접근)
API-Info      (t3.micro)  = 2 vCPU  ← 재활용 정보 (DB 직접 접근)
PostgreSQL    (t3.medium) = 2 vCPU  ← Stateful DB
Redis         (t3.small)  = 2 vCPU  ← 캐시/세션
RabbitMQ      (t3.small)  = 2 vCPU  ← 메시지 큐
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
합계:                     14 vCPU ✅ (여유 2 vCPU)
```

**도쿄 리전 (ap-northeast-1) - 14 vCPU**:
```
API-Location  (t3.micro)  = 2 vCPU  ← 위치 (외부 API 호출)
API-Character (t3.micro)  = 2 vCPU  ← 캐릭터 (사용 빈도 낮음, 신규)
API-Scan      (t3.small)  = 2 vCPU  ← 스캔 (AI Worker 연계)
API-Chat      (t3.small)  = 2 vCPU  ← 챗봇 (외부 LLM 호출)
Worker-Storage(t3.small)  = 2 vCPU  ← S3 업로드 (비동기)
Worker-AI     (t3.small)  = 2 vCPU  ← AI 처리 (비동기)
Monitoring    (t3.medium) = 2 vCPU  ← Prometheus/Grafana
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
합계:                     14 vCPU ✅
```

**설정 방법**:

1. **Terraform 모듈 업데이트** (`terraform/main.tf`):
```hcl
# 이름 변경 및 신규 추가
module "api_my" { ... }          # userinfo → my
module "api_info" { ... }        # recycle_info → info  
module "api_scan" { ... }        # waste → scan
module "api_chat" { ... }        # chat_llm → chat
module "api_character" { ... }   # 신규 추가 (t3.micro)

# 도쿄 리전 프로바이더 추가
provider "aws" {
  alias  = "tokyo"
  region = "ap-northeast-1"
}
```

2. **VPC Peering 자동 설정**:
   - 서울 ↔ 도쿄 리전 간 Private 통신
   - RabbitMQ, PostgreSQL 접근 가능
   - 데이터 전송 비용: ~$0.09/GB (예상 $0.45/월)

3. **Kubernetes 크로스 리전 설정**:
   - 도쿄 노드를 서울 Master에 조인
   - NodeSelector로 리전별 Pod 배치
   - 지연시간: 5-10ms (허용 가능)

**재배치 계획** (한도 증가 후):
```bash
# 1. 도쿄 리소스를 서울로 마이그레이션
./scripts/utilities/migrate-tokyo-to-seoul.sh

# 2. Terraform으로 자동 재배치
terraform apply -var="enable_multi_region=false"
```

**장점**:
- ✅ 성능 저하 없음
- ✅ 필수 API 7개 모두 사용 가능
- ✅ 한도 증가 후 쉬운 재배치
- ✅ API Character 추가 가능

**단점**:
- ⚠️ 약간의 추가 비용 (~$0.45/월)
- ⚠️ 네트워크 설정 복잡도 증가
- ⚠️ 리전 간 지연 5-10ms

**커밋**: `feat: Add multi-region deployment strategy for 14-node architecture`

---

#### 해결 방법 3: 인스턴스 타입 다운그레이드 (비권장)

⚠️ **성능 저하 심각** - 개발/테스트용으로만

`terraform.tfvars` 생성:
```hcl
master_instance_type = "t3.small"   # 2 vCPU (기존: medium)
api_instance_type = "t3.nano"       # 0.5 vCPU (기존: micro)
worker_instance_type = "t3.micro"   # 2 vCPU (기존: small)
infra_instance_type = "t3.nano"     # 0.5 vCPU (기존: micro/small)
```

**총 vCPU**: ~12 (한도 내)

❌ **문제점**:
- PostgreSQL, RabbitMQ 성능 저하
- API 응답 시간 증가
- Worker 처리 속도 감소

---

### 3.2. ResourceAlreadyExistsException

#### 문제
```
Error: Only one open service quota increase request is allowed per quota.
```

**원인**: 이미 진행 중인 한도 증가 요청이 있음

#### 확인
```bash
aws service-quotas list-requested-service-quota-change-history-by-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region ap-northeast-2 \
    --query 'RequestedQuotas[?Status==`PENDING` || Status==`CASE_OPENED`]'
```

**Status**:
- `CASE_OPENED`: AWS가 검토 중 (좋은 신호!)
- `PENDING`: 대기 중
- `APPROVED`: 승인 완료
- `DENIED`: 거절 (드물음)

#### 해결
기존 요청이 처리될 때까지 대기 (5-10분마다 한도 확인)

---

## 4. 스크립트 실행 문제

### 4.1. InvalidKeyPair.Duplicate

#### 문제
```
Error: importing EC2 Key Pair (k8s-cluster-key): InvalidKeyPair.Duplicate
```

**원인**: 이전 Key Pair가 삭제되지 않음

#### 해결
`destroy-with-cleanup.sh`에 Key Pair 정리 추가:

```bash
KEY_NAME="k8s-cluster-key"
if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    aws ec2 delete-key-pair --key-name "$KEY_NAME" --region "$AWS_REGION"
fi
```

---

### 4.2. BucketAlreadyOwnedByYou

#### 문제
```
Error: creating S3 Bucket (prod-sesacthon-images): BucketAlreadyOwnedByYou
```

**원인**: S3 버킷이 삭제되지 않고 남아있음

#### 해결
`destroy-with-cleanup.sh`에 S3 Bucket 정리 추가:

```bash
BUCKETS=$(aws s3api list-buckets \
    --query "Buckets[?starts_with(Name, 'prod-sesacthon')].Name" \
    --output text)

for bucket in $BUCKETS; do
    # 버킷 내용물 삭제
    aws s3 rm "s3://$bucket" --recursive
    # 버킷 삭제
    aws s3api delete-bucket --bucket "$bucket" --region "$AWS_REGION"
done
```

---

## 5. GitHub CLI 인증 문제

### 5.1. Missing Required Scope

#### 문제
```
error validating token: missing required scope 'read:org'
```

**원인**: GitHub Personal Access Token에 필요한 scope 누락

#### 해결 방법 1: 대화형 로그인 (권장)

```bash
gh auth login
# GitHub.com 선택
# HTTPS 선택
# Login with a web browser 선택
# 브라우저에서 코드 입력
```

#### 해결 방법 2: 새 PAT 생성

1. https://github.com/settings/tokens 접속
2. "Generate new token (classic)" 클릭
3. 필요한 scopes 선택:
   - ✅ `repo` (전체)
   - ✅ `read:org`
   - ✅ `write:packages`
4. 토큰 생성 후:
```bash
echo "<your-token>" | gh auth login --with-token
```

#### 해결 방법 3: GitHub Web UI (수동)

1. Repository → Settings → Secrets and variables → Actions
2. Secret 등록:
   - `GITHUB_USERNAME`: `mangowhoiscloud`
3. Variable 등록:
   - `VERSION`: `v0.6.0`

⚠️ **주의**: `GITHUB_TOKEN`은 GitHub Actions에서 자동으로 제공되므로 등록 불필요

---

## 6. CloudFront 관련 문제

### 6.1. CloudFront 생성 시간

#### 현상
```
aws_cloudfront_distribution.images: Still creating... [6m0s elapsed]
```

**원인**: CloudFront distribution 생성은 전세계 edge location에 배포되므로 시간 소요

**정상 범위**: 5-15분

**확인**:
```bash
aws cloudfront get-distribution --id <distribution-id> \
    --query 'Distribution.Status'
```

**Status**:
- `InProgress`: 배포 중 (정상)
- `Deployed`: 배포 완료

---

### 6.2. CloudFront 삭제 필요성

#### 문제
CloudFront가 남아있으면:
- S3 버킷 삭제 불가
- 비용 지속 발생 ($0.085/GB + 요청 비용)
- Route53 레코드 충돌

#### 해결
`destroy-with-cleanup.sh`에 CloudFront 정리 추가:

```bash
# 1. Distribution disable
CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json)
ETAG=$(echo "$CONFIG" | jq -r '.ETag')
NEW_CONFIG=$(echo "$CONFIG" | jq '.DistributionConfig | .Enabled = false')

aws cloudfront update-distribution \
    --id "$dist_id" \
    --if-match "$ETAG" \
    --distribution-config "$NEW_CONFIG"

# 2. Disabled 상태 대기 (2분)
sleep 120

# 3. Distribution 삭제
FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$dist_id" --output json)
FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag')

aws cloudfront delete-distribution --id "$dist_id" --if-match "$FINAL_ETAG"
```

**소요 시간**: 5-10분

---

### 6.3. CloudFront 검색 로직 부족으로 인한 ACM Certificate 삭제 실패

#### 문제
```
🔐 ACM Certificate 정리 (us-east-1)...
⚠️  ACM Certificate 발견:
  - 도메인: images.growbin.app
    ARN: arn:aws:acm:us-east-1:...:certificate/...
    ⚠️  Certificate가 아직 사용 중입니다:
       - arn:aws:cloudfront::...:distribution/E1GGDPUBLRQG59
    ⏳ CloudFront 완전 삭제 대기 중 (최대 10분)...
       ⏳ 대기 중... (120초 경과)
       ... (계속 대기)
```

**원인**: CloudFront Distribution이 검색되지 않아 삭제되지 않음

**근본 원인**:
```bash
# 기존 검색 쿼리 (문제)
CF_DISTRIBUTIONS=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(Origins.Items[].DomainName, 'sesacthon-images')].Id" \
    --output text)
```

- S3 버킷 이름(`sesacthon-images`)만 검색
- ACM Certificate를 사용하는 다른 Origin의 Distribution은 검색 안 됨
- 결과: CloudFront가 Enable 상태로 남아있음 → ACM Certificate 삭제 불가

---

#### 진단

**CloudFront Distribution 상태 확인**:
```bash
# Distribution ID 확인
aws cloudfront list-distributions \
    --query "DistributionList.Items[*].{Id:Id,Status:Status,Enabled:DistributionConfig.Enabled,Aliases:Aliases.Items}" \
    --output table

# 특정 Distribution 상세 확인
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.{Status:Status,Enabled:DistributionConfig.Enabled,DomainName:DomainName}' \
    --output json
```

**예상 결과 (문제 상황)**:
```json
{
    "Status": "Deployed",
    "Enabled": true,  // ⚠️ 여전히 활성화 상태
    "DomainName": "d3f4l2e8xigfr9.cloudfront.net"
}
```

---

#### 해결 방법 1: 스크립트 개선 (권장)

`destroy-with-cleanup.sh`의 CloudFront 검색 로직 개선:

```bash
# 5-1. CloudFront Distribution 확인 및 삭제
echo "🌐 CloudFront Distribution 확인..."

# 1. S3 버킷 기반 검색
CF_DISTRIBUTIONS_S3=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(Origins.Items[].DomainName, 'sesacthon-images')].Id" \
    --output text 2>/dev/null || echo "")

# 2. ACM Certificate 기반 검색 (images. 도메인)
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

#### 해결 방법 2: 수동 해결 (즉시 필요 시)

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

# 2. Disabled 상태 대기 (2-5분)
echo "⏳ CloudFront Disabled 대기 중..."
sleep 180

# 3. CloudFront Distribution 삭제
FINAL_CONFIG=$(aws cloudfront get-distribution-config --id "$DIST_ID" --output json)
FINAL_ETAG=$(echo "$FINAL_CONFIG" | jq -r '.ETag')

aws cloudfront delete-distribution \
    --id "$DIST_ID" \
    --if-match "$FINAL_ETAG"

# 4. ACM Certificate 삭제 (CloudFront 삭제 완료 후 5분 대기)
echo "⏳ CloudFront 완전 삭제 대기 중..."
sleep 300

aws acm delete-certificate \
    --certificate-arn "arn:aws:acm:us-east-1:721622471953:certificate/b34e6013-babe-4495-88f6-77f4d9bdd39f" \
    --region us-east-1
```

---

#### 예방 방법

**배포 시 태그 추가**:
```hcl
# terraform/cloudfront.tf
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

**스크립트에서 태그 기반 검색**:
```bash
# 태그 기반 검색 (가장 확실함)
CF_DISTRIBUTIONS_TAG=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Tags.Items[?Key=='SearchKey' && Value=='sesacthon-cleanup']].Id" \
    --output text 2>/dev/null || echo "")
```

---

#### 디버깅 명령어

```bash
# 1. 모든 CloudFront Distribution 목록
aws cloudfront list-distributions \
    --query "DistributionList.Items[*].{Id:Id,DomainName:DomainName,Status:Status,Enabled:DistributionConfig.Enabled}" \
    --output table

# 2. ACM Certificate 사용 여부 확인
aws acm describe-certificate \
    --certificate-arn "arn:aws:acm:us-east-1:...:certificate/..." \
    --region us-east-1 \
    --query 'Certificate.{InUseBy:InUseBy,Status:Status}' \
    --output json

# 3. Distribution의 Origin 확인
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.DistributionConfig.Origins.Items[*].DomainName' \
    --output json

# 4. Distribution의 Certificate 확인
aws cloudfront get-distribution --id E1GGDPUBLRQG59 \
    --query 'Distribution.DistributionConfig.ViewerCertificate' \
    --output json
```

---

#### 관련 커밋

- `fix: Improve CloudFront detection logic to include ACM Certificate-based search`
- `fix: Add multiple search strategies for CloudFront Distribution cleanup`

---

## 7. VPC 삭제 지연 문제

### 7.1. VPC 삭제가 15분 이상 소요되는 문제

#### 현상
```
module.vpc.aws_vpc.main: Still destroying... [id=vpc-02562955fe60907d8, 15m30s elapsed]
aws_acm_certificate.cdn: Still destroying... [id=arn:aws:acm:..., 15m30s elapsed]
```

**원인**: AWS 리소스가 완전히 삭제되지 않은 상태에서 VPC 삭제 시도

#### 주요 원인 분석

##### 1. NAT Gateway 삭제 지연 (가장 큰 원인)

**문제**:
- NAT Gateway는 삭제 시 **3-5분** 소요
- 기존 스크립트는 30초만 대기 후 다음 단계로 진행
- NAT Gateway가 완전히 삭제되지 않으면 VPC 삭제 불가

**해결**:
```bash
# NAT Gateway 완전 삭제 대기 (최대 5분)
MAX_NAT_WAIT=300  # 5분
NAT_WAIT_COUNT=0

while [ $NAT_WAIT_COUNT -lt $MAX_NAT_WAIT ]; do
    REMAINING_NATS=$(aws ec2 describe-nat-gateways \
        --filter "Name=vpc-id,Values=$VPC_ID" "Name=state,Values=available,pending,deleting" \
        --region "$AWS_REGION" \
        --query 'NatGateways[*].NatGatewayId' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$REMAINING_NATS" ]; then
        echo "✅ 모든 NAT Gateway 삭제 완료 (${NAT_WAIT_COUNT}초 소요)"
        break
    fi
    
    if [ $((NAT_WAIT_COUNT % 30)) -eq 0 ]; then
        echo "⏳ 대기 중... (${NAT_WAIT_COUNT}초 경과)"
    fi
    
    sleep 5
    NAT_WAIT_COUNT=$((NAT_WAIT_COUNT + 5))
done
```

##### 2. ENI (Elastic Network Interface) 삭제 실패

**문제**:
- NAT Gateway와 연결된 ENI가 자동 삭제되지 않음
- 5초 대기 후 재시도하지만 여전히 실패 가능
- ENI가 VPC에 연결되어 있어 VPC 삭제 불가

**해결**:
```bash
# ENI는 NAT Gateway 삭제 후에 자동으로 해제되므로 여러 번 재시도
MAX_ENI_RETRY=3
ENI_RETRY_COUNT=0

while [ $ENI_RETRY_COUNT -lt $MAX_ENI_RETRY ]; do
    ENI_IDS=$(aws ec2 describe-network-interfaces \
        --filters "Name=vpc-id,Values=$VPC_ID" \
        --region "$AWS_REGION" \
        --query 'NetworkInterfaces[?Status==`available`].NetworkInterfaceId' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$ENI_IDS" ]; then
        echo "✅ 남은 ENI 없음"
        break
    fi
    
    echo "⚠️  남은 ENI 발견 (시도 $((ENI_RETRY_COUNT + 1))/$MAX_ENI_RETRY):"
    
    for eni in $ENI_IDS; do
        aws ec2 delete-network-interface --network-interface-id "$eni" --region "$AWS_REGION" 2>/dev/null || true
    done
    
    ENI_RETRY_COUNT=$((ENI_RETRY_COUNT + 1))
    
    if [ $ENI_RETRY_COUNT -lt $MAX_ENI_RETRY ]; then
        echo "⏳ 10초 후 재시도..."
        sleep 10
    fi
done
```

##### 3. ACM Certificate 삭제 지연

**문제**:
- CloudFront가 ACM Certificate를 사용 중이면 삭제 불가
- CloudFront disable 후 2분만 대기하는데, 실제로는 5-10분 소요
- Certificate가 삭제되지 않으면 Terraform destroy가 계속 대기

**해결**:
```bash
# CloudFront 사용 여부 확인
CERT_IN_USE=$(aws acm describe-certificate \
    --certificate-arn "$cert_arn" \
    --region us-east-1 \
    --query 'Certificate.InUseBy' \
    --output json 2>/dev/null || echo "[]")

IN_USE_COUNT=$(echo "$CERT_IN_USE" | jq '. | length' 2>/dev/null || echo "0")

if [ "$IN_USE_COUNT" -gt 0 ]; then
    echo "⚠️  Certificate가 아직 사용 중입니다:"
    
    # CloudFront 완전 삭제 대기 (최대 10분)
    MAX_CF_WAIT=600  # 10분
    CF_WAIT_COUNT=0
    
    while [ $CF_WAIT_COUNT -lt $MAX_CF_WAIT ]; do
        CURRENT_IN_USE=$(aws acm describe-certificate \
            --certificate-arn "$cert_arn" \
            --region us-east-1 \
            --query 'Certificate.InUseBy' \
            --output json 2>/dev/null || echo "[]")
        
        CURRENT_COUNT=$(echo "$CURRENT_IN_USE" | jq '. | length' 2>/dev/null || echo "0")
        
        if [ "$CURRENT_COUNT" -eq 0 ]; then
            echo "✅ Certificate 해제 완료 (${CF_WAIT_COUNT}초 소요)"
            break
        fi
        
        if [ $((CF_WAIT_COUNT % 30)) -eq 0 ]; then
            echo "⏳ 대기 중... (${CF_WAIT_COUNT}초 경과)"
        fi
        
        sleep 10
        CF_WAIT_COUNT=$((CF_WAIT_COUNT + 10))
    done
fi
```

---

### 7.2. 리소스 삭제 순서 최적화

#### 권장 순서

```
1. Kubernetes 리소스 삭제 (Ingress, Service, PVC)
   └─> ALB, Target Groups 자동 삭제
   
2. AWS 리소스 확인 및 삭제
   ├─> Load Balancer 삭제 (최대 60초 대기)
   ├─> Security Groups 삭제
   ├─> ENI 삭제 (재시도 3회)
   ├─> Target Groups 삭제
   ├─> CloudFront Distribution 삭제 (최대 10분 대기)
   ├─> Route53 레코드 삭제
   ├─> S3 Bucket 정리
   ├─> ACM Certificate 삭제 (CloudFront 대기 최대 10분)
   └─> IAM Policy 강제 정리

3. NAT Gateway 삭제 (최대 5분 대기) ⭐ 중요!
   └─> 완전 삭제 확인 후 다음 단계 진행

4. VPC Endpoints 삭제
   VPC Peering Connections 삭제
   Elastic IP 해제

5. Terraform destroy 실행
   └─> VPC 및 나머지 리소스 삭제
```

---

### 7.3. 수동 디버깅 명령어

#### VPC 삭제를 막는 리소스 확인

```bash
# 1. NAT Gateway 상태 확인
aws ec2 describe-nat-gateways \
    --filter "Name=vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'NatGateways[*].[NatGatewayId,State]' \
    --output table

# 2. ENI 확인
aws ec2 describe-network-interfaces \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'NetworkInterfaces[*].[NetworkInterfaceId,Status,Description]' \
    --output table

# 3. Security Groups 확인
aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'SecurityGroups[*].[GroupId,GroupName]' \
    --output table

# 4. Subnets 확인
aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock]' \
    --output table

# 5. Internet Gateway 확인
aws ec2 describe-internet-gateways \
    --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'InternetGateways[*].[InternetGatewayId]' \
    --output table

# 6. VPC Endpoints 확인
aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region ap-northeast-2 \
    --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]' \
    --output table

# 7. ACM Certificate 사용 여부 확인
aws acm describe-certificate \
    --certificate-arn "$CERT_ARN" \
    --region us-east-1 \
    --query 'Certificate.InUseBy' \
    --output json
```

#### 수동 리소스 삭제

```bash
# NAT Gateway 강제 삭제
NAT_GW_ID="nat-xxxxx"
aws ec2 delete-nat-gateway --nat-gateway-id "$NAT_GW_ID" --region ap-northeast-2

# ENI 강제 삭제
ENI_ID="eni-xxxxx"
aws ec2 delete-network-interface --network-interface-id "$ENI_ID" --region ap-northeast-2

# VPC 직접 삭제 시도
VPC_ID="vpc-xxxxx"
aws ec2 delete-vpc --vpc-id "$VPC_ID" --region ap-northeast-2
```

---

### 7.4. 예상 소요 시간

| 단계 | 소요 시간 | 설명 |
|-----|----------|------|
| Kubernetes 리소스 정리 | 30초-1분 | Ingress, Service, PVC 삭제 |
| Load Balancer 삭제 | 1-2분 | ALB 완전 삭제 대기 |
| CloudFront 삭제 | 5-10분 | Distribution disable + 삭제 |
| ACM Certificate 대기 | 5-10분 | CloudFront 해제 대기 |
| **NAT Gateway 삭제** | **3-5분** | ⭐ 가장 시간 소요 |
| Terraform destroy | 2-3분 | 나머지 리소스 삭제 |
| **총 예상 시간** | **15-30분** | 정상 범위 |

---

### 7.5. 개선 결과

#### 기존 문제
- NAT Gateway: 30초만 대기 → 완전 삭제되지 않음
- ENI: 1회 재시도 → 삭제 실패
- ACM Certificate: 대기 없음 → Terraform이 계속 대기

#### 개선 후
- ✅ NAT Gateway: 최대 5분 대기 → 완전 삭제 확인
- ✅ ENI: 3회 재시도 (10초 간격) → 삭제 성공률 향상
- ✅ ACM Certificate: 최대 10분 대기 → CloudFront 해제 확인 후 삭제

**결과**: VPC 삭제 지연 문제 해결 및 안정적인 cleanup 가능

---

### 7.6. 관련 커밋

- `fix: Add comprehensive NAT Gateway deletion wait in destroy-with-cleanup.sh`
- `fix: Improve ENI deletion with retry mechanism`
- `fix: Add CloudFront deletion wait for ACM Certificate cleanup`

---

## 8. ArgoCD 리디렉션 루프 문제

### 문제
브라우저에서 `https://argocd.growbin.app` 접속 시 "리디렉션한 횟수가 너무 많습니다" 에러 발생.

### 원인
- Ingress가 포트 443을 사용하지만 `backend-protocol: HTTP`가 설정되지 않음
- ALB가 HTTPS로 연결 시도하지만 ArgoCD는 HTTP만 지원
- Health Check 실패로 Target Group이 unhealthy 상태

### 해결
1. Ingress `backend-protocol`을 HTTP로 변경
2. Service Port를 443 → 80으로 변경
3. Health Check 경로 설정 (`/healthz`)
4. ArgoCD ConfigMap에 `server.insecure: true` 추가

**자세한 내용:** [ARGOCD_REDIRECT_LOOP.md](./troubleshooting/ARGOCD_REDIRECT_LOOP.md)

---

## 9. Prometheus 메모리 부족 문제

### 문제
Prometheus Pod가 `Pending` 상태로 스케줄링되지 않음.

### 원인
- Prometheus가 2Gi 메모리를 요청
- Monitoring 노드(t3.small, 2GB RAM)의 Allocatable 메모리가 부족
- 에러: `9 Insufficient memory`

### 해결
1. **옵션 1 (권장):** Prometheus 리소스 요청을 2Gi → 1.5Gi로 감소
2. **옵션 2:** Monitoring 노드 인스턴스 타입을 t3.medium(4GB RAM)으로 업그레이드
3. **옵션 3:** Prometheus를 다른 노드로 스케줄링

**자세한 내용:** [PROMETHEUS_MEMORY_INSUFFICIENT.md](./troubleshooting/PROMETHEUS_MEMORY_INSUFFICIENT.md)

---

## 10. Atlantis Pod CrashLoopBackOff 문제

### 문제
Atlantis Pod가 `CrashLoopBackOff` 상태로 계속 재시작됨.

### 원인
1. **포트 파싱 에러**: Atlantis가 환경 변수에서 포트를 파싱할 때 Service의 ClusterIP 형식을 포트로 인식
2. **권한 문제**: PersistentVolume에 대한 쓰기 권한 없음 (`fsGroup`, `runAsUser` 설정 누락)

### 해결
1. 포트 명시적 설정 (`--port=4141`)
2. SecurityContext 추가 (`fsGroup: 1000`, `runAsUser: 1000`, `runAsGroup: 1000`)

**자세한 내용:** [ATLANTIS_POD_CRASHLOOPBACKOFF.md](./troubleshooting/ATLANTIS_POD_CRASHLOOPBACKOFF.md)

---

## 11. 베스트 프랙티스

### 10.1. 재구축 전 체크리스트

```bash
# 1. vCPU 한도 확인
aws service-quotas get-service-quota \
    --service-code ec2 \
    --quota-code L-1216C47A \
    --region ap-northeast-2 \
    --query 'Quota.Value'
# 결과: 32.0 이상이어야 함

# 2. 이전 리소스 완전 정리
./scripts/maintenance/destroy-with-cleanup.sh

# 3. 환경 변수 설정
export GITHUB_TOKEN="<your-token>"
export GITHUB_USERNAME="<your-username>"
export VERSION="v0.6.0"

# 4. 재구축 실행
./scripts/cluster/auto-rebuild.sh
```

---

### 8.2. 디버깅 명령어 모음

```bash
# Terraform 상태 확인
terraform state list
terraform output -json

# AWS 리소스 확인
aws ec2 describe-instances --region ap-northeast-2
aws iam list-policies --scope Local
aws s3api list-buckets

# Kubernetes 상태 확인
kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -A

# GitHub 인증 상태
gh auth status

# 로그 확인
tail -f /var/log/cloud-init-output.log  # Master 노드에서
journalctl -u kubelet -f                 # Worker 노드에서
```

---

### 8.3. 문제 발생 시 대응 순서

1. **에러 메시지 확인**: 정확한 에러 내용 파악
2. **이 문서 검색**: 유사한 문제 해결 방법 확인
3. **AWS 상태 확인**: 리소스가 실제로 남아있는지 확인
4. **정리 스크립트 실행**: `destroy-with-cleanup.sh`
5. **한도 확인**: vCPU, IAM Policy 등
6. **재시도**: 정리 후 재구축

---

## 12. 참고 문서

- [AWS Service Quotas Documentation](https://docs.aws.amazon.com/servicequotas/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [GitHub CLI Authentication](https://cli.github.com/manual/gh_auth_login)
- [CloudFront Developer Guide](https://docs.aws.amazon.com/cloudfront/)

---

## 13. 지원

문제가 해결되지 않으면:
- GitHub Issues: https://github.com/mangowhoiscloud/backend/issues
- AWS Support: https://console.aws.amazon.com/support/
- Terraform Registry: https://discuss.hashicorp.com/

---

**최종 업데이트**: 2025-11-07  
**버전**: v0.6.0  
**아키텍처**: 14-Node Microservices + Worker Local SQLite WAL

