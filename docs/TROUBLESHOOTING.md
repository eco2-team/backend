# Troubleshooting Guide - 이코에코(Eco²)

> 13-Node Microservices Architecture + Worker Local SQLite WAL 구축 과정에서 발생한 문제 및 해결 방안

## 📋 목차

- [1. Terraform 관련 문제](#1-terraform-관련-문제)
- [2. IAM Policy 중복 문제](#2-iam-policy-중복-문제)
- [3. AWS 한도 관련 문제](#3-aws-한도-관련-문제)
- [4. 스크립트 실행 문제](#4-스크립트-실행-문제)
- [5. GitHub CLI 인증 문제](#5-github-cli-인증-문제)
- [6. CloudFront 관련 문제](#6-cloudfront-관련-문제)

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

**원인**: 13-Node 아키텍처 필요 vCPU (26) > 계정 한도 (16)

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

#### 해결 방법 2: 인스턴스 타입 다운그레이드 (임시)

⚠️ **성능 저하 있음** - 개발/테스트용으로만 권장

`terraform.tfvars` 생성:
```hcl
master_instance_type = "t3a.small"   # 2 vCPU (기존: large)
api_instance_type = "t3a.micro"      # 2 vCPU (기존: medium)
worker_instance_type = "t3a.medium"  # 2 vCPU (기존: large)
infra_instance_type = "t3a.micro"    # 2 vCPU (기존: medium)
```

**총 vCPU**: 16 (한도 내)

**커밋**: `feat: Add vCPU quota increase request script`

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

## 7. 베스트 프랙티스

### 7.1. 재구축 전 체크리스트

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

### 7.2. 디버깅 명령어 모음

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

### 7.3. 문제 발생 시 대응 순서

1. **에러 메시지 확인**: 정확한 에러 내용 파악
2. **이 문서 검색**: 유사한 문제 해결 방법 확인
3. **AWS 상태 확인**: 리소스가 실제로 남아있는지 확인
4. **정리 스크립트 실행**: `destroy-with-cleanup.sh`
5. **한도 확인**: vCPU, IAM Policy 등
6. **재시도**: 정리 후 재구축

---

## 8. 참고 문서

- [AWS Service Quotas Documentation](https://docs.aws.amazon.com/servicequotas/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [GitHub CLI Authentication](https://cli.github.com/manual/gh_auth_login)
- [CloudFront Developer Guide](https://docs.aws.amazon.com/cloudfront/)

---

## 9. 지원

문제가 해결되지 않으면:
- GitHub Issues: https://github.com/mangowhoiscloud/backend/issues
- AWS Support: https://console.aws.amazon.com/support/
- Terraform Registry: https://discuss.hashicorp.com/

---

**최종 업데이트**: 2025-11-07  
**버전**: v0.6.0  
**아키텍처**: 13-Node Microservices + Worker Local SQLite WAL

