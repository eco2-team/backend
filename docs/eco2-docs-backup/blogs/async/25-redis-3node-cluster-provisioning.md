# Message Queue #15: Redis 3-Node 클러스터 인프라 프로비저닝

> **작업 일시**: 2025-12-26  
> **목표**: 단일 Redis → 용도별 3노드 분리 (Auth, Streams, Cache)  
> **이전 문서**: [#14 Redis Streams SSE 전환](./24-redis-streams-sse-migration.md)

---

## 배경

### 기존 구조의 문제

```
┌─────────────────────────────────────────────────────────────┐
│  단일 Redis (k8s-redis, t3.medium)                          │
│                                                              │
│  DB 0: JWT Blacklist (보안, noeviction 필요)                │
│  DB 1: Celery Result (휘발성, LRU eviction 가능)            │
│  DB 2: SSE Streams (휘발성, 빠른 응답 필요)                  │
│  DB 3: OAuth State (보안, noeviction 필요)                  │
│  ...                                                         │
│                                                              │
│  ❌ 문제:                                                    │
│  - eviction 정책 충돌 (보안 vs 캐시)                        │
│  - 장애 시 전체 시스템 영향                                 │
│  - 용도별 리소스 튜닝 불가                                  │
└─────────────────────────────────────────────────────────────┘
```

### 목표 구조

```
┌─────────────────────────────────────────────────────────────┐
│  k8s-redis-auth (t3.medium)                                  │
│  ├─ JWT Blacklist + OAuth State                              │
│  ├─ Policy: noeviction (보안 데이터 보호)                   │
│  └─ Storage: PVC (AOF 영속성)                               │
├─────────────────────────────────────────────────────────────┤
│  k8s-redis-streams (t3.small)                                │
│  ├─ SSE 이벤트 (Redis Streams)                              │
│  ├─ Policy: noeviction (이벤트 유실 방지)                   │
│  └─ Storage: emptyDir (휘발성, TTL 자동 정리)               │
├─────────────────────────────────────────────────────────────┤
│  k8s-redis-cache (t3.small)                                  │
│  ├─ Celery Result + Domain Cache                             │
│  ├─ Policy: allkeys-lru (메모리 부족 시 eviction)           │
│  └─ Storage: emptyDir (휘발성)                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 인프라 변경

### EC2 노드 변경

| 구분 | 기존 | 변경 |
|------|------|------|
| 노드 수 | 1 (k8s-redis) | 3 (auth, streams, cache) |
| 인스턴스 | t3.medium x1 | t3.medium x1 + t3.small x2 |
| vCPU | 2 | 2 + 2 + 2 = 6 |
| 메모리 | 4GB | 4GB + 2GB + 2GB = 8GB |

### Kubernetes 라벨 전략

```yaml
# 기존
k8s-redis:
  labels:
    infra-type: redis
  taints:
    - domain=data:NoSchedule

# 변경: 노드별 전용 라벨
k8s-redis-auth:
  labels:
    redis-cluster: auth
k8s-redis-streams:
  labels:
    redis-cluster: streams
k8s-redis-cache:
  labels:
    redis-cluster: cache
```

### RedisFailover CR nodeAffinity

```yaml
# 각 Redis Pod는 전용 노드에만 스케줄링
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: redis-cluster
              operator: In
              values:
                - auth  # 또는 streams, cache
```

---

## 프로비저닝 절차

### Phase 1: Terraform Plan (사전 검증)

```bash
cd terraform

# 전체 plan (위험!)
terraform plan -var="dockerhub_password=xxx" -out=full.plan
# ⚠️ 결과: 24 to add, 2 to change, 15 to destroy
# 원인: AMI 버전 변경으로 모든 노드 replace 시도
```

**교훈**: `data.aws_ami.ubuntu`가 최신 AMI를 참조하면서 모든 인스턴스가 재생성 대상이 됨.

### Phase 1.5: Target 옵션으로 Redis만 적용

```bash
# Redis 모듈만 타겟팅
terraform plan \
  -var="dockerhub_password=xxx" \
  -target=module.redis \
  -target=module.redis_auth \
  -target=module.redis_streams \
  -target=module.redis_cache \
  -out=redis-only.plan

# 결과: 3 to add, 0 to change, 1 to destroy ✅
```

### Phase 2: vCPU 제한 확인

```bash
# 현재 사용량
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].InstanceType' \
  --output text | tr '\t' '\n' | sort | uniq -c

# vCPU 한계
aws service-quotas get-service-quota \
  --service-code ec2 \
  --quota-code L-1216C47A \
  --query 'Quota.Value'
# 결과: 43
```

### Phase 2.5: 문제 발생 - vCPU 한계 초과

```
Error: VcpuLimitExceeded: You have requested more vCPU capacity 
than your current vCPU limit of 43 allows
```

**원인 분석**:

| 타입 | 개수 | vCPU | 소계 |
|------|------|------|------|
| t3.xlarge | 1 | 4 | 4 |
| t3.large | 3 | 2 | 6 |
| t3.medium | 7 | 2 | 14 |
| t3.small | 9 | 2 | 18 |
| **합계** | - | - | **42 vCPU** |

새 Redis 3노드 추가 시: 42 + 6 = 48 > 43 (한계 초과)

### Phase 3: 고아 인스턴스 발견 및 정리

Terraform apply 중간 실패로 고아 인스턴스 생성됨:

```bash
# 고아 인스턴스 확인
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=k8s-redis-*" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],State.Name]'

# Terraform State에 없는 인스턴스 발견
# i-xxx (k8s-redis-auth)    - State 없음
# i-xxx (k8s-redis-streams) - State 없음 (중복)
# i-xxx (k8s-redis-cache)   - State 없음 (중복)
```

**정리 절차**:

```bash
# 1. 고아 인스턴스 삭제
aws ec2 terminate-instances --instance-ids \
  i-0d260a8fce6435125 \
  i-0937f4cc4108e310e \
  i-07c259439a85e5888

# 2. Terraform State에서 중복 제거
terraform state rm module.redis_cache.aws_instance.this
terraform state rm module.redis_streams.aws_instance.this

# 3. 삭제 완료 대기
aws ec2 wait instance-terminated --instance-ids ...
```

### Phase 4: vCPU 여유 확보 후 재시도

```bash
# 정리 후 vCPU 계산
# 현재: 36 vCPU (17개 인스턴스)
# 필요: +6 vCPU (3개 Redis)
# 최종: 42 vCPU < 43 (한계) ✅

# 새로운 Plan
terraform plan \
  -var="dockerhub_password=xxx" \
  -target=module.redis_auth \
  -target=module.redis_streams \
  -target=module.redis_cache \
  -out=redis-fresh.plan

terraform apply redis-fresh.plan
```

---

## 교훈 및 Best Practices

### 1. AMI Lifecycle 관리

```hcl
# modules/ec2/main.tf
resource "aws_instance" "this" {
  # ...
  lifecycle {
    ignore_changes = [ami]  # AMI 변경 무시
  }
}
```

### 2. vCPU 한계 사전 확인

```bash
# 프로비저닝 전 반드시 확인
CURRENT=$(aws ec2 describe-instances ... | wc -l)
LIMIT=$(aws service-quotas get-service-quota ... | jq '.Quota.Value')
NEEDED=6  # 새로 추가할 vCPU

if [ $((CURRENT + NEEDED)) -gt $LIMIT ]; then
  echo "⚠️ vCPU 한계 초과 예상"
fi
```

### 3. Target 옵션 활용

```bash
# 항상 영향 범위 제한
terraform plan -target=module.specific_module
```

### 4. State 불일치 복구

```bash
# 고아 리소스 확인
terraform plan  # "not in configuration" 표시 확인

# State 정리
terraform state rm <resource>

# 또는 import
terraform import module.xxx.aws_instance.this <instance-id>
```

---

## 다음 단계

1. ~~Terraform Apply 완료~~ ✅
2. ~~Ansible Join: 새 노드 클러스터 조인~~ ✅
3. **ArgoCD Sync**: RedisFailover CR 배포 → [#16 Redis Operator 배포](./26-redis-operator-deployment.md)
4. **환경변수 전파**: 애플리케이션 재시작
5. **k6 부하 테스트**: SSE 50 VU 재검증

---

## Commits & PR

### Pull Request

- **PR #225**: [feat: Redis 3-node Cluster + Redis Streams SSE Migration](https://github.com/eco2-team/backend/pull/225)

### Commits

| Hash | Message |
|------|---------|
| `5c63a0c` | feat: Redis 3-node cluster + Redis Streams SSE migration |
| `a8a8d8f` | style: terraform fmt outputs.tf |
| `9bb0eab` | ci: add Redis service for scan tests |
| `ab9e1b7` | ci: add domains/_shared/events to scan triggers |

---

## 관련 문서

- [#14 Redis Streams SSE 전환](./24-redis-streams-sse-migration.md)
- [#13 SSE 50 VU 병목 분석](./23-sse-bottleneck-analysis-50vu.md)
- [workloads/redis/README.md](../../../workloads/redis/README.md) - Redis 인프라 상세
- [scripts/provisioning/redis-nodes-add.md](../../../scripts/provisioning/redis-nodes-add.md) - 명령어 가이드

