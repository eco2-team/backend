# 🏗️ 네임스페이스 전략 분석: 현재 vs 베스트 프랙티스

**문서 버전**: v0.7.2  
**최종 업데이트**: 2025-11-13  
**작성자**: Architecture Team

---

## 🎯 의사결정 요약

**현재 전략**: 도메인별 완전 격리 (Option 1 적용)

**상태**: ✅ **적용 완료** (Kustomize + Ansible + NetworkPolicy)

---

## 📊 적용된 네임스페이스 구조

### 1️⃣ 실제 구성 (v0.8.0)

| 네임스페이스 | 용도 | 배포 리소스 | NetworkPolicy |
|------------|------|------------|--------------|
| `auth` | 인증/인가 API | auth-api | ✅ |
| `my` | 마이페이지 API | my-api | ✅ |
| `scan` | 쓰레기 분류 API | scan-api | ✅ |
| `character` | 캐릭터 API | character-api | ✅ |
| `location` | 위치 기반 API | location-api | ✅ |
| `info` | 재활용 정보 API | info-api | ✅ |
| `chat` | AI 챗봇 API | chat-api | ✅ |
| `data` | 인프라 계층 | postgresql, redis, rabbitmq | ✅ |
| `monitoring` | 모니터링 | prometheus, grafana, node-exporter | ✅ |
| `atlantis` | GitOps | atlantis | ❌ |
| `kube-system` | Kubernetes 코어 | calico-node, coredns, kube-proxy, ebs-csi | - |

### 2️⃣ 적용 스택

```yaml
# Kustomize: 도메인별 네임스페이스 분리
k8s/overlays/auth/kustomization.yaml:
  namespace: auth  # ← 변경 완료

# ArgoCD: ApplicationSet 자동 배포
argocd/applications/ecoeco-appset-kustomize.yaml:
  destination:
    namespace: '{{domain}}'  # ← 동적 네임스페이스

# Ansible: 네임스페이스 생성 자동화
ansible/playbooks/10-namespaces.yml:
  - 네임스페이스 생성
  - NetworkPolicy 적용

# NetworkPolicy: 도메인별 격리
k8s/networkpolicies/domain-isolation.yaml:
  - API → Data 계층 접근 제어
  - 도메인 간 격리
```

```yaml
# k8s/overlays/*/kustomization.yaml
현재 사용 중인 네임스페이스:

api:              # 7개 API 서비스 (통합)
  - auth-api
  - my-api
  - scan-api
  - character-api
  - location-api
  - info-api
  - chat-api

monitoring:       # 모니터링 스택
  - prometheus
  - grafana
  - node-exporter
  - servicemonitor

atlantis:         # Terraform GitOps
  - atlantis

kube-system:      # Kubernetes 시스템
  - calico-node
  - coredns
  - kube-proxy
  - aws-load-balancer-controller
  - ebs-csi-controller
```

### 2️⃣ Helm Chart 정의 (참고용)

```yaml
# charts/ecoeco-backend/templates/namespaces.yaml
# ⚠️ 2025-11-13 정리: workers, data, messaging 제거

현재 정의:
api:              # ✅ 사용 중 (Kustomize overlays)

이전 정의 (제거됨):
workers:          # ❌ 미사용
data:             # ❌ 미사용
messaging:        # ❌ 미사용
```

**참고**: Helm Chart는 참고용으로만 유지. 실제 배포는 Kustomize 사용.  
**문서**: `charts/README.md`, `docs/architecture/gitops/08-GITOPS_TOOLING_DECISION.md`

---

## 🏆 Kubernetes 베스트 프랙티스

### Google Kubernetes Engine (GKE) 권장사항

#### 1. 환경별 분리
```yaml
# 환경 격리 전략
production:
  - 프로덕션 워크로드
  - 엄격한 리소스 제한
  - 프로덕션 DB 접근

staging:
  - 스테이징 테스트
  - 프로덕션과 유사한 환경
  - 별도 DB 사용

development:
  - 개발 워크로드
  - 느슨한 리소스 제한
  - 개발 DB 사용
```

**우리 상황**: 
- ✅ 단일 환경 (프로덕션)
- ⚠️ 환경별 분리 불필요 (해커톤 MVP)

#### 2. 팀/도메인별 분리
```yaml
# 멀티 테넌트 격리
team-frontend:
  - React 애플리케이션
  - Nginx Ingress
  
team-backend:
  - API 서비스
  - Worker 서비스

team-data:
  - PostgreSQL
  - Redis
  - RabbitMQ
```

**우리 상황**:
- ⚠️ 단일 백엔드 팀
- ⚠️ 팀별 분리 불필요

#### 3. 기능/레이어별 분리
```yaml
# 아키텍처 레이어별 격리
frontend:
  - Web UI
  - Mobile API Gateway

backend:
  - API Services
  - Business Logic

data:
  - Databases
  - Caches
  - Message Queues

workers:
  - Background Jobs
  - Batch Processing
```

**우리 상황**:
- ✅ 부분적 적용 (monitoring, atlantis 분리)
- ⚠️ API, Worker, Data 혼재

---

## 🔍 현재 구조 분석

### 장점 ✅

#### 1. 단순성
```yaml
장점:
- 네임스페이스 개수 최소화 (3개)
- Cross-namespace 통신 불필요
- NetworkPolicy 단순화
- 관리 포인트 감소

예시:
auth-api → my-api 호출:
  http://my-api.api.svc.cluster.local:8000
  → 동일 네임스페이스, DNS 간단
```

#### 2. 리소스 할당 유연성
```yaml
장점:
- 네임스페이스별 ResourceQuota 불필요
- API 간 자유로운 리소스 공유
- 스케일링 유연성

예시:
scan-api가 일시적으로 많은 리소스 필요 시:
  → 다른 API의 여유 리소스 사용 가능
```

#### 3. 배포 단순화
```yaml
장점:
- 단일 Kustomize overlay
- ApplicationSet 단순화
- Secret/ConfigMap 공유 용이

현재 구조:
k8s/overlays/auth/
  kustomization.yaml:
    namespace: api  # ← 통일
```

### 단점 ❌

#### 1. 격리 부족
```yaml
문제:
- 모든 API가 동일 네임스페이스
- NetworkPolicy 적용 어려움
- 보안 경계 불명확

예시:
auth-api가 scan-api에 직접 접근 가능:
  → 의도하지 않은 의존성 발생 가능
```

#### 2. RBAC 복잡도
```yaml
문제:
- 도메인별 권한 분리 불가
- ServiceAccount 공유
- 세밀한 접근 제어 어려움

예시:
auth 개발자가 scan-api도 수정 가능:
  → 최소 권한 원칙 위반
```

#### 3. 리소스 경합
```yaml
문제:
- ResourceQuota 적용 불가
- 특정 API의 리소스 독점 가능
- 공정한 리소스 분배 어려움

예시:
scan-api가 메모리 누수 시:
  → 다른 API도 영향받음 (OOMKilled)
```

#### 4. 모니터링 복잡도
```yaml
문제:
- 네임스페이스별 메트릭 집계 불가
- 도메인별 비용 추적 어려움
- 알림 정책 세분화 제한

예시:
Prometheus Query:
  sum(rate(http_requests_total[5m])) by (namespace)
  → 모두 "api"로 표시 (구분 불가)
```

---

## 📐 베스트 프랙티스 적용 시나리오

### Option 1: 도메인별 분리 (권장) ⭐⭐⭐

#### 구조
```yaml
# 마이크로서비스 도메인별 격리
auth:
  - auth-api
  - auth-worker (향후)

my:
  - my-api

scan:
  - scan-api
  - scan-worker (storage, ai)

character:
  - character-api

location:
  - location-api

info:
  - info-api

chat:
  - chat-api
  - chat-worker (향후)

# Infrastructure
data:
  - postgresql
  - redis
  - rabbitmq

# Observability
monitoring:
  - prometheus
  - grafana
  - node-exporter

# GitOps
atlantis:
  - atlantis
```

#### 장점
```yaml
✅ 명확한 도메인 경계
✅ NetworkPolicy 적용 가능
✅ RBAC 세분화 (도메인별 권한)
✅ ResourceQuota 적용 (공정한 리소스 분배)
✅ 모니터링 정확성 (도메인별 메트릭)
✅ 장애 격리 (한 도메인 장애가 다른 도메인에 영향 최소화)
```

#### 단점
```yaml
❌ 복잡도 증가 (네임스페이스 14개)
❌ Cross-namespace 통신 설정 필요
❌ NetworkPolicy 관리 증가
❌ DNS 이름 길어짐 (auth-api.auth.svc.cluster.local)
❌ Secret/ConfigMap 중복 가능성
```

#### 마이그레이션 예시
```yaml
# Before (현재)
k8s/overlays/auth/kustomization.yaml:
  namespace: api
  namePrefix: auth-

# After (도메인별)
k8s/overlays/auth/kustomization.yaml:
  namespace: auth      # ← 변경
  namePrefix: ""       # ← 제거 (불필요)
  
  resources:
    - namespace.yaml   # ← 추가
    - ../../base
```

---

### Option 2: 레이어별 분리 (중간) ⭐⭐

#### 구조
```yaml
# 아키텍처 레이어별 격리
api:              # API 레이어
  - auth-api
  - my-api
  - scan-api
  - character-api
  - location-api
  - info-api
  - chat-api

workers:          # Worker 레이어
  - storage-worker
  - ai-worker

data:             # Data 레이어
  - postgresql
  - redis
  - rabbitmq

monitoring:       # Observability
  - prometheus
  - grafana

atlantis:         # GitOps
  - atlantis
```

#### 장점
```yaml
✅ 레이어별 명확한 구분
✅ 네임스페이스 개수 적절 (5개)
✅ 관리 복잡도 낮음
✅ API 간 통신 간단 (동일 네임스페이스)
```

#### 단점
```yaml
❌ 도메인별 격리 불가
❌ API 간 NetworkPolicy 적용 불가
❌ 도메인별 RBAC 불가
```

---

### Option 3: 현재 유지 (최소) ⭐

#### 구조
```yaml
# 현재 구조 유지
api:              # 모든 API
monitoring:       # 모니터링
atlantis:         # GitOps
kube-system:      # 시스템
```

#### 장점
```yaml
✅ 변경 불필요 (안정성)
✅ 최소 복잡도
✅ 빠른 개발 속도
```

#### 단점
```yaml
❌ 베스트 프랙티스 미준수
❌ 격리 부족
❌ 확장성 제한
```

---

## 📊 세 가지 옵션 비교

| 항목 | 현재 유지 | 레이어별 분리 | 도메인별 분리 |
|------|----------|-------------|-------------|
| **네임스페이스 개수** | 3개 | 5개 | 14개 |
| **관리 복잡도** | 낮음 | 중간 | 높음 |
| **도메인 격리** | ❌ | ⚠️ | ✅ |
| **NetworkPolicy** | ❌ | ⚠️ | ✅ |
| **RBAC 세분화** | ❌ | ⚠️ | ✅ |
| **ResourceQuota** | ❌ | ⚠️ | ✅ |
| **모니터링 정확성** | ❌ | ⚠️ | ✅ |
| **장애 격리** | ❌ | ⚠️ | ✅ |
| **배포 속도** | ✅ | ⚠️ | ❌ |
| **학습 곡선** | ✅ | ⚠️ | ❌ |
| **확장성** | ❌ | ⚠️ | ✅ |
| **마이그레이션 비용** | - | 낮음 | 높음 |

---

## 🎯 우리 프로젝트 상황 분석

### 현재 요구사항

```yaml
프로젝트 특성:
- 해커톤 MVP (1개월)
- 단일 백엔드 팀 (1명)
- 14-Node 마이크로서비스
- Self-Managed Kubernetes 학습 목적

우선순위:
1. 빠른 개발 속도 ✅
2. 안정성 (변경 최소화) ✅
3. 학습 가치 ⚠️
4. 베스트 프랙티스 준수 ⚠️
```

### 단계별 로드맵

```yaml
Phase 1: MVP (현재) - 현재 유지 ✅
목표: 빠른 개발
전략: 네임스페이스 최소화 (api, monitoring, atlantis)
기간: 2025-11-13 ~ 해커톤 종료

Phase 2: 본선 준비 (선택적) - 레이어별 분리
목표: 안정성 향상
전략: api → api + workers + data 분리
기간: 본선 진출 시

Phase 3: 프로덕션 (장기) - 도메인별 분리
목표: 베스트 프랙티스 준수
전략: 도메인별 완전 격리
기간: 정식 서비스 출시 시
```

---

## 🚀 권장 전략

### 현재 (MVP): Option 3 유지 ✅

#### 이유
```yaml
✅ 변경 리스크 최소화
✅ 배포 속도 최대화
✅ 관리 복잡도 최소화
✅ 해커톤 기간 내 안정성 확보

현재 구조로도 충분:
- 7개 API가 안정적으로 동작 중
- NetworkPolicy 없어도 문제 없음 (신뢰된 환경)
- RBAC 세분화 불필요 (단일 팀)
- ResourceQuota 불필요 (14-Node로 충분한 리소스)
```

#### 단, 개선 필요한 부분

```yaml
1. Helm Chart 정의 정리
문제: workers, data, messaging 네임스페이스 정의되었지만 미사용
해결: 
  - charts/ecoeco-backend/templates/namespaces.yaml 수정
  - workers, data, messaging 제거
  - api만 유지

2. 문서 일관성
문제: 여러 문서에서 네임스페이스 구조가 다르게 표현됨
해결:
  - 모든 문서에서 "api 단일 네임스페이스" 명시
  - "권장 구조 (향후 개선)" 섹션 추가
```

---

## 📝 마이그레이션 가이드 (향후 참고)

### Phase 2: 레이어별 분리 시

#### 1단계: 네임스페이스 생성
```yaml
# k8s/namespaces/
apiVersion: v1
kind: Namespace
metadata:
  name: workers
---
apiVersion: v1
kind: Namespace
metadata:
  name: data
```

#### 2단계: Kustomize 수정
```yaml
# k8s/overlays/storage/kustomization.yaml
namespace: workers  # api → workers

# k8s/overlays/ai/kustomization.yaml
namespace: workers  # api → workers
```

#### 3단계: Service DNS 업데이트
```yaml
# Before
postgresql.api.svc.cluster.local

# After
postgresql.data.svc.cluster.local
```

#### 4단계: NetworkPolicy 추가
```yaml
# k8s/network-policies/allow-api-to-data.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-api-to-data
  namespace: data
spec:
  podSelector: {}
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: api
```

#### 5단계: ArgoCD ApplicationSet 수정
```yaml
# argocd/applications/ecoeco-appset-kustomize.yaml
spec:
  template:
    spec:
      destination:
        namespace: "{{namespace}}"  # ← 동적 할당
```

---

## 🔖 관련 문서

### 내부 문서
- [네트워크 및 네임스페이스 검증](./network-and-namespace-verification.md) - 현재 구조 상세
- [Label & Annotation 체계](../infrastructure/k8s-label-annotation-system.md) - 레이블 전략
- [서비스 아키텍처](./03-SERVICE_ARCHITECTURE.md) - 14-Node 전체 구조
- [GitOps 파이프라인](../deployment/GITOPS_PIPELINE_KUSTOMIZE.md) - 배포 구조

### 외부 문서
- [Kubernetes Namespaces Best Practices](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/)
- [Google: Namespace Design Patterns](https://cloud.google.com/kubernetes-engine/docs/best-practices/enterprise-multitenancy)
- [CNCF: Multi-Tenancy in Kubernetes](https://www.cncf.io/blog/2020/07/21/kubernetes-multi-tenancy/)

---

## 📈 메트릭 및 모니터링 고려사항

### 현재 구조 (단일 네임스페이스)

```promql
# Namespace별 메트릭 불가능
sum(rate(http_requests_total[5m])) by (namespace)
# 결과: api = 모든 API 합산 (구분 불가)

# 해결책: Label 기반 그룹화
sum(rate(http_requests_total[5m])) by (app)
# 결과: auth, my, scan, ... 각각 표시 ✅
```

### 도메인별 분리 시

```promql
# Namespace별 명확한 메트릭
sum(rate(http_requests_total[5m])) by (namespace)
# 결과: auth, my, scan, ... 각각 표시 ✅

# 비용 추적 가능
sum(container_memory_usage_bytes) by (namespace)
# 결과: 도메인별 리소스 사용량
```

---

## ✅ 최종 권장사항

### 현재 (2025-11-13)

```yaml
전략: Option 3 유지 (현재 구조)

이유:
✅ 해커톤 MVP에 최적화
✅ 안정성 최우선
✅ 빠른 개발 속도
✅ 관리 복잡도 최소

개선 작업:
1. Helm Chart 정리 (미사용 네임스페이스 제거)
2. 문서 일관성 확보
3. 향후 마이그레이션 가이드 작성 (완료)
```

### 향후 (본선 진출 시)

```yaml
전략: Option 2 검토 (레이어별 분리)

조건:
- 본선 진출 확정
- 2주 이상 여유 기간
- 안정적인 마이그레이션 가능

마이그레이션:
- api → api + workers + data 분리
- NetworkPolicy 추가
- ResourceQuota 설정
```

### 장기 (프로덕션)

```yaml
전략: Option 1 적용 (도메인별 분리)

조건:
- 정식 서비스 출시
- 운영팀 구성
- 멀티 테넌트 필요

마이그레이션:
- 도메인별 완전 격리
- RBAC 세분화
- NetworkPolicy 강화
```

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-11-13 | v0.7.2 | 초안 작성 - 현재 구조 vs 베스트 프랙티스 비교, 3가지 옵션 제시, 단계별 로드맵 |
| 2025-11-13 | v0.7.2 | Helm Chart 정리 - workers, data, messaging 네임스페이스 제거, 문서 업데이트 |
| 2025-11-13 | v0.7.2 | **Option 1 적용 완료** - 도메인별 네임스페이스 분리 (auth, my, scan, character, location, info, chat, data, monitoring), NetworkPolicy 생성, Kustomize + ArgoCD + Ansible 전체 스택 업데이트 |

---

## ✍️ 결론

**도메인별 완전 격리 전략이 적용되었습니다!** ✅

```yaml
이전: api 단일 네임스페이스
현재: 도메인별 완전 격리 (Option 1)
적용: Kustomize + ArgoCD ApplicationSet + Ansible + NetworkPolicy

개선 사항:
✅ 도메인 간 완전 격리 (Zero Trust)
✅ NetworkPolicy로 트래픽 제어
✅ Data 계층 접근 제어
✅ ArgoCD 자동 배포 (동적 네임스페이스)
✅ Ansible 자동화 (네임스페이스 + NetworkPolicy)

향후:
- Atlantis 네임스페이스 NetworkPolicy 추가
- ResourceQuota 설정 (필요 시)
- PodDisruptionBudget 추가 (HA 필요 시)
```

**베스트 프랙티스를 조기에 적용하여 확장 가능한 아키텍처를 구축했습니다!** 🚀

---

**작성일**: 2025-11-13  
**상태**: ✅ **Option 1 적용 완료 (도메인별 완전 격리)**  
**다음 검토**: 프로덕션 출시 시 (ResourceQuota, PodDisruptionBudget 추가)

