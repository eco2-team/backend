# Troubleshooting: VPC 삭제 지연 및 Security Group 삭제 실패

## 📋 목차

- [문제 상황](#문제-상황)
- [증상](#증상)
- [근본 원인](#근본-원인)
- [해결 방법](#해결-방법)
- [예방 조치](#예방-조치)
- [관련 이슈](#관련-이슈)

---

## 문제 상황

### 발생 시점
- `destroy-with-cleanup.sh` 실행 중
- Terraform destroy 단계에서 VPC 삭제 시

### 문제 요약
VPC 삭제가 5분 이상 지연되며, 최종적으로 타임아웃이나 삭제 실패로 이어질 수 있습니다.

---

## 증상

### 1. Terraform 로그에서 확인되는 증상

```bash
module.vpc.aws_vpc.main: Destroying... [id=vpc-01a27920f8b2bde8c]
module.vpc.aws_vpc.main: Still destroying... [10s elapsed]
module.vpc.aws_vpc.main: Still destroying... [20s elapsed]
module.vpc.aws_vpc.main: Still destroying... [30s elapsed]
...
module.vpc.aws_vpc.main: Still destroying... [5m0s elapsed]
module.vpc.aws_vpc.main: Still destroying... [5m10s elapsed]
```

### 2. 수동 확인 시 발견되는 문제

```bash
# Security Groups 확인
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=vpc-01a27920f8b2bde8c" \
  --region ap-northeast-2

# 출력 예시
| sg-08e944a6d85bceef3 | k8s-growbinalb-c3e75def63        |
| sg-08f4995a728906f6d | k8s-traffic-sesacthon-db59a6b266 |
| sg-0c57f8a1aef58bcab | default                          |
```

**문제**: Kubernetes ALB Controller가 생성한 Security Groups가 VPC에 남아있음

---

## 근본 원인

### 1. Kubernetes가 생성한 AWS 리소스의 생명주기 문제

Kubernetes는 다음 AWS 리소스를 **Terraform 외부**에서 직접 생성합니다:

| 컴포넌트 | 생성하는 AWS 리소스 | 문제점 |
|---------|-------------------|--------|
| ALB Controller | ALB, Target Groups, Security Groups | Terraform이 인식하지 못함 |
| EBS CSI Driver | EBS Volumes | PVC 삭제 시 자동 삭제되지 않을 수 있음 |
| Service (LoadBalancer) | Classic Load Balancers | Terraform이 관리하지 않음 |

### 2. Security Group 간 순환 참조

```
┌─────────────────────────────────────────────────────┐
│ k8s-growbinalb (ALB용 Security Group)               │
│  ↓ Ingress 규칙: k8s-traffic 허용                   │
├─────────────────────────────────────────────────────┤
│ k8s-traffic (Worker 노드 간 통신용)                  │
│  ↓ Ingress 규칙: k8s-growbinalb 허용                │
└─────────────────────────────────────────────────────┘
```

**결과**: 서로 참조하고 있어 Terraform이 삭제 순서를 결정할 수 없음

### 3. ALB 삭제 비동기 처리

```
ALB 삭제 요청 (즉시 반환)
    ↓
ALB 상태: "active" → "deleting" (수 초 ~ 수십 초 소요)
    ↓
Security Group 해제 (ALB 완전 삭제 후)
    ↓
Security Group 삭제 가능
```

**문제**: 기존 스크립트는 ALB 삭제 요청 후 10초만 대기하고 다음 단계로 진행
→ Security Group이 여전히 ALB에 의해 사용 중

### 4. ENI (Elastic Network Interface) Detaching 시간

- ALB/EC2 삭제 직후 ENI는 `detaching` 상태
- 완전히 detach되기까지 5-15초 소요
- 이 기간 동안 ENI 삭제 시도는 실패

---

## 해결 방법

### Option 1: 수동 삭제 (긴급 상황)

#### Step 1: 현재 상태 확인

```bash
VPC_ID="vpc-01a27920f8b2bde8c"  # Terraform output에서 확인
AWS_REGION="ap-northeast-2"

# Security Groups 확인
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=k8s-*" \
  --region $AWS_REGION \
  --query 'SecurityGroups[*].{ID:GroupId,Name:GroupName}' \
  --output table
```

#### Step 2: ALB 확인 및 삭제

```bash
# ALB 확인
aws elbv2 describe-load-balancers \
  --region $AWS_REGION \
  --query "LoadBalancers[?VpcId==\`$VPC_ID\`].{Name:LoadBalancerName,ARN:LoadBalancerArn}" \
  --output table

# ALB 삭제
ALB_ARN="arn:aws:elasticloadbalancing:..."  # 위에서 확인한 ARN
aws elbv2 delete-load-balancer \
  --load-balancer-arn $ALB_ARN \
  --region $AWS_REGION

# ALB 완전 삭제 대기 (30-60초)
echo "ALB 삭제 대기 중..."
sleep 60
```

#### Step 3: Security Group 규칙 정리 및 삭제

```bash
# Security Group ID 목록
SG1="sg-08e944a6d85bceef3"  # k8s-growbinalb
SG2="sg-08f4995a728906f6d"  # k8s-traffic

# SG1 규칙 삭제
INGRESS1=$(aws ec2 describe-security-group-rules \
  --group-ids $SG1 \
  --region $AWS_REGION \
  --query 'SecurityGroupRules[?IsEgress==`false`].SecurityGroupRuleId' \
  --output text)

for rule in $INGRESS1; do
  aws ec2 revoke-security-group-ingress \
    --group-id $SG1 \
    --security-group-rule-ids $rule \
    --region $AWS_REGION
done

EGRESS1=$(aws ec2 describe-security-group-rules \
  --group-ids $SG1 \
  --region $AWS_REGION \
  --query 'SecurityGroupRules[?IsEgress==`true`].SecurityGroupRuleId' \
  --output text)

for rule in $EGRESS1; do
  aws ec2 revoke-security-group-egress \
    --group-id $SG1 \
    --security-group-rule-ids $rule \
    --region $AWS_REGION
done

# SG2도 동일하게 처리
# ...

# Security Group 삭제
sleep 5
aws ec2 delete-security-group --group-id $SG1 --region $AWS_REGION
aws ec2 delete-security-group --group-id $SG2 --region $AWS_REGION
```

#### Step 4: Terraform destroy 재시도

```bash
cd terraform
terraform destroy -auto-approve
```

---

### Option 2: 자동화 스크립트 사용 (권장)

**개선된 `destroy-with-cleanup.sh` 사용**

#### 개선 내용

1. **Security Group 실패 추적**
   ```bash
   declare -a FAILED_SGS
   
   # 삭제 실패 시 배열에 추가
   FAILED_SGS+=("$sg:$SG_NAME")
   ```

2. **ALB 완전 삭제 대기**
   ```bash
   MAX_WAIT=60
   while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
     REMAINING_ALBS=$(aws elbv2 describe-load-balancers ...)
     if [ -z "$REMAINING_ALBS" ]; then
       break
     fi
     sleep 2
   done
   ```

3. **실패한 Security Group 재시도**
   ```bash
   if [ ${#FAILED_SGS[@]} -gt 0 ]; then
     for sg_info in "${FAILED_SGS[@]}"; do
       # 규칙 재정리
       # 삭제 재시도
     done
   fi
   ```

4. **ENI 재시도 로직**
   ```bash
   if aws ec2 delete-network-interface ... 2>/dev/null; then
     echo "✅ 삭제 성공"
   else
     sleep 5
     aws ec2 delete-network-interface ...  # 재시도
   fi
   ```

#### 사용 방법

```bash
./scripts/maintenance/destroy-with-cleanup.sh
```

**예상 소요 시간**: 3-5분 (기존 7-10분에서 50% 단축)

---

## 예방 조치

### 1. 인프라 설계 시 고려사항

#### Kubernetes 외부 리소스 관리 전략

```yaml
# Option A: Terraform으로 미리 생성 (권장)
# - ALB를 Terraform으로 생성
# - TargetGroupBinding으로 Kubernetes Service 연결

# Option B: 자동 정리 메커니즘 구현
# - Kubernetes Finalizer 활용
# - Pre-delete Hook 구현
```

#### Security Group 설계

```hcl
# terraform/security-groups.tf

# ALB Security Group
resource "aws_security_group" "alb" {
  name_prefix = "alb-"
  vpc_id      = module.vpc.vpc_id
  
  lifecycle {
    create_before_destroy = true
  }
}

# Worker Security Group
resource "aws_security_group" "workers" {
  name_prefix = "workers-"
  vpc_id      = module.vpc.vpc_id
  
  lifecycle {
    create_before_destroy = true
  }
}

# 순환 참조 방지: 별도 규칙 리소스로 분리
resource "aws_security_group_rule" "alb_to_workers" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "-1"
  security_group_id        = aws_security_group.workers.id
  source_security_group_id = aws_security_group.alb.id
}
```

### 2. destroy-with-cleanup.sh 정기 테스트

```bash
# 개발 환경에서 주기적으로 테스트
# - 클러스터 생성
# - 완전 삭제
# - 남은 리소스 확인

./scripts/cluster/build-cluster.sh
# ... 테스트 ...
./scripts/maintenance/destroy-with-cleanup.sh

# 남은 리소스 확인
aws ec2 describe-vpcs --filters "Name=is-default,Values=false" --region ap-northeast-2
aws ec2 describe-security-groups --filters "Name=group-name,Values=k8s-*" --region ap-northeast-2
```

### 3. 모니터링 및 알림

```bash
# CloudWatch Alarm 설정 (예시)
# - VPC 삭제 시간 > 5분 → 알림
# - 미사용 Security Group 감지 → 알림
# - 미사용 ENI 감지 → 알림
```

---

## 관련 이슈

### 비슷한 문제들

1. **NAT Gateway 삭제 지연**
   - 원인: NAT Gateway 삭제 시 3-5분 소요
   - 해결: `destroy-with-cleanup.sh`에 NAT Gateway 확인 및 삭제 로직 추가됨

2. **VPC Endpoints 남아있음**
   - 원인: Terraform이 VPC Endpoints를 인식하지 못함
   - 해결: `destroy-with-cleanup.sh`에 VPC Endpoints 확인 및 삭제 로직 추가됨

3. **VPC Peering Connections**
   - 원인: 수동으로 생성한 Peering Connection이 남아있음
   - 해결: `destroy-with-cleanup.sh`에 확인 로직 추가됨

### 관련 AWS 문서

- [Working with Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)
- [Delete your VPC](https://docs.aws.amazon.com/vpc/latest/userguide/working-with-vpcs.html#VPC_Deleting)
- [Elastic Network Interfaces](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-eni.html)
- [Application Load Balancer Deletion](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-delete.html)

### AWS Support Case 참고 사항

VPC 삭제가 10분 이상 지연되는 경우:

1. AWS Console에서 VPC 상태 확인
2. Dependency 확인
   - Security Groups
   - Network Interfaces
   - NAT Gateways
   - Internet Gateways
3. AWS Support에 Case 생성 시 포함할 정보:
   - VPC ID
   - 삭제 시도 시각
   - 남아있는 리소스 목록
   - CloudTrail 로그

---

## 체크리스트

### 문제 발생 시

- [ ] Terraform destroy 로그 확인 (어느 리소스에서 멈췄는지)
- [ ] VPC ID 확인
- [ ] Security Groups 목록 확인 (`k8s-*` 패턴)
- [ ] ALB 존재 여부 확인
- [ ] ENI 상태 확인
- [ ] NAT Gateway 상태 확인

### 수동 해결 시

- [ ] ALB 삭제
- [ ] ALB 완전 삭제 대기 (60초)
- [ ] Security Group 규칙 정리
- [ ] Security Group 삭제
- [ ] ENI 삭제
- [ ] Terraform destroy 재시도
- [ ] VPC 삭제 확인

### 예방 조치

- [ ] `destroy-with-cleanup.sh` 최신 버전 사용
- [ ] 개발 환경에서 정기적으로 완전 삭제 테스트
- [ ] CloudWatch Alarm 설정
- [ ] Security Group 설계 검토 (순환 참조 방지)

---

## 변경 이력

| 날짜 | 작성자 | 변경 내용 |
|------|--------|----------|
| 2025-11-04 | Infrastructure Team | 초안 작성 |
| 2025-11-04 | Infrastructure Team | destroy-with-cleanup.sh 개선 사항 반영 |

---

## 참고 링크

- [MANUAL_OPERATIONS_TO_IAC.md](./MANUAL_OPERATIONS_TO_IAC.md) - 수동 작업 → IaC 반영 문서
- [TROUBLESHOOTING_ALB_PROVIDER_ID.md](./TROUBLESHOOTING_ALB_PROVIDER_ID.md) - Provider ID 문제 해결 가이드
- [../scripts/maintenance/destroy-with-cleanup.sh](../scripts/maintenance/destroy-with-cleanup.sh) - 개선된 삭제 스크립트

