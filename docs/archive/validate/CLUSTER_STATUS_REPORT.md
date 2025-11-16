# 클러스터 상태 점검 보고서
**점검 일시:** 2025-11-15  
**대상 클러스터:** k8s-master (13.124.12.134)

---

## 📊 종합 상태 요약

### ✅ 정상 동작 중인 컴포넌트
- **ArgoCD**: 모든 Pod Running (7개 Pod)
- **Atlantis**: Running (StatefulSet)
- **모니터링 스택**: Prometheus, Grafana, Alertmanager 모두 Running
- **메시징**: RabbitMQ Running (RabbitMQ Operator 정상)
- **캐시**: Redis Running
- **Ingress**: ALB 기반 Ingress 12개 생성됨
- **네임스페이스**: 모든 도메인 네임스페이스 생성됨 (17개)

### ⚠️ 문제가 있는 컴포넌트
- **PostgreSQL**: CreateContainerConfigError (Secret 이름 불일치)
  - 참조: `postgres-secret` (없음)
  - 실제: `postgresql-secret` (존재함)

### ❌ 배포되지 않은 컴포넌트
- **ArgoCD Applications**: 없음 (root-app 미배포)
- **API Services**: 모든 서비스 미배포 (auth, character, chat, info, location, my, scan)
- **Workers**: Celery Workers 미배포

---

## 🔍 상세 분석

### 1. ArgoCD 상태

**Pod 상태:**
```
✅ argocd-application-controller-0        Running
✅ argocd-applicationset-controller       Running
✅ argocd-dex-server                      Running
✅ argocd-notifications-controller        Running
✅ argocd-redis                           Running
✅ argocd-repo-server                     Running
✅ argocd-server                          Running
```

**Applications 상태:**
```
❌ Applications: 0개
❌ ApplicationSets: 0개
```

**접근 URL:**
- `https://argocd.growbin.app` (Ingress 설정됨)

### 2. 코드베이스 vs 클러스터 차이

| 항목 | 코드베이스 | 클러스터 | 상태 |
|------|-----------|---------|------|
| root-app.yaml | ✅ 존재 (develop 브랜치) | ❌ 미배포 | **불일치** |
| App-of-Apps 구조 | ✅ 완성됨 (10개 파일) | ❌ 없음 | **불일치** |
| API Services | ✅ ApplicationSet 정의됨 | ❌ 배포 안됨 | **불일치** |
| Workers | ✅ Application 정의됨 | ❌ 배포 안됨 | **불일치** |
| Namespaces | ✅ 정의됨 | ✅ 생성됨 | **일치** |
| Ingress | ✅ 정의됨 | ✅ 생성됨 | **일치** |

### 3. ArgoCD Applications 구조 (코드베이스)

```
argocd/
├── root-app.yaml                    # App of Apps 루트
└── apps/
    ├── 00-namespaces.yaml          # Wave -1: Namespaces
    ├── 10-infrastructure.yaml       # Wave 10
    ├── 20-alb-controller.yaml       # Wave 20: ALB Controller
    ├── 20-platform.yaml             # Wave 20
    ├── 30-platform.yaml             # Wave 30
    ├── 40-monitoring.yaml           # Wave 40: Prometheus Stack
    ├── 50-data-operators.yaml       # Wave 50: RabbitMQ Operator
    ├── 60-data-clusters.yaml        # Wave 60: PostgreSQL/Redis/RabbitMQ
    ├── 70-gitops-tools.yaml         # Wave 70: Atlantis
    ├── 80-apis-app-of-apps.yaml     # Wave 80: API Services + Workers
    └── apis/
        ├── auth-api.yaml
        ├── character-api.yaml
        ├── chat-api.yaml
        ├── info-api.yaml
        ├── location-api.yaml
        ├── my-api.yaml
        ├── scan-api.yaml
        └── workers/
            ├── celery-workers.yaml
            ├── celery-worker/kustomization.yaml
            └── flower/kustomization.yaml
```

**주요 특징:**
- `targetRevision: develop` (모든 Application)
- Wave 기반 순차 배포 (-1 → 80)
- ApplicationSet으로 7개 API 서비스 자동 생성

### 4. 네임스페이스 현황

```
✅ argocd            - ArgoCD 운영
✅ atlantis          - Atlantis GitOps Tool
✅ auth              - 인증 API (배포 대기)
✅ character         - 캐릭터 API (배포 대기)
✅ chat              - 채팅 API (배포 대기)
✅ data              - PostgreSQL, Redis
✅ info              - 정보 API (배포 대기)
✅ kube-system       - 쿠버네티스 시스템
✅ location          - 위치 API (배포 대기)
✅ messaging         - RabbitMQ
✅ monitoring        - Prometheus, Grafana
✅ my                - 마이페이지 API (배포 대기)
✅ rabbitmq-system   - RabbitMQ Operator
✅ scan              - 스캔 API (배포 대기)
```

### 5. Ingress 현황

**ALB Address:** `k8s-ecoecomain-f37ee763b5-2088518262.ap-northeast-2.elb.amazonaws.com`

| Host | Namespace | 서비스 상태 |
|------|-----------|-----------|
| argocd.growbin.app | argocd | ✅ Running |
| atlantis.growbin.app | atlantis | ✅ Running |
| prometheus.growbin.app | monitoring | ✅ Running |
| grafana.growbin.app | monitoring | ✅ Running |
| api.growbin.app/auth | auth | ❌ 서비스 없음 |
| api.growbin.app/character | character | ❌ 서비스 없음 |
| api.growbin.app/chat | chat | ❌ 서비스 없음 |
| api.growbin.app/info | info | ❌ 서비스 없음 |
| api.growbin.app/location | location | ❌ 서비스 없음 |
| api.growbin.app/my | my | ❌ 서비스 없음 |
| api.growbin.app/scan | scan | ❌ 서비스 없음 |

### 6. 데이터 계층 상태

**PostgreSQL:**
```
❌ Status: CreateContainerConfigError
⚠️  Secret 이름 불일치:
   - StatefulSet 참조: postgres-secret (Not Found)
   - 실제 존재: postgresql-secret (Opaque, 3 keys)
✅ PVC: Bound (50Gi, gp3)
✅ PV: Bound
```

**Redis:**
```
✅ Status: Running
✅ Deployment: 1/1 Ready
✅ Service: 10.111.40.69:6379
```

**RabbitMQ:**
```
✅ Status: Running (RabbitMQ Operator)
✅ StatefulSet: 1/1 Ready
✅ Service: 10.100.47.32:5672, 15672
✅ RabbitMQCluster: AllReplicasReady=True
```

### 7. 모니터링 스택 상태

```
✅ Prometheus: Running
✅ Grafana: Running
✅ Alertmanager: Running
✅ Node Exporters: 14개 노드에서 Running
✅ Kube State Metrics: Running
```

### 8. PersistentVolume 현황

| PVC | Namespace | Size | Status |
|-----|-----------|------|--------|
| postgres-storage-postgres-0 | data | 50Gi | ✅ Bound |
| persistence-rabbitmq-server-0 | messaging | 10Gi | ✅ Bound |
| atlantis-data-atlantis-0 | atlantis | 20Gi | ✅ Bound |
| prometheus-db | monitoring | 50Gi | ✅ Bound |

---

## 🎯 주요 발견 사항

### 1. ArgoCD 미사용 상태
- ArgoCD는 설치되었으나 **실제 배포에 사용되지 않음**
- 인프라는 **Ansible Playbook으로 수동 배포**된 것으로 추정
- GitOps 파이프라인이 **구축되지 않은 상태**

### 2. 코드베이스와 클러스터 완전 불일치
- 코드베이스: App-of-Apps 패턴으로 완성된 GitOps 구조
- 클러스터: ArgoCD Application이 하나도 없음
- **GitOps 전환 준비는 되었으나 실행 안됨**

### 3. 브랜치 불일치 가능성
- ArgoCD 설정: `targetRevision: develop`
- 현재 로컬 브랜치: `main`
- develop 브랜치 확인 필요

### 4. PostgreSQL 수정 필요
- Secret 이름을 `postgres-secret`으로 변경 또는
- StatefulSet에서 `postgresql-secret` 참조하도록 수정

---

## 📋 다음 조치 사항

### 즉시 조치 (Critical)

1. **PostgreSQL Secret 수정**
   ```bash
   kubectl create secret generic postgres-secret \
     --from-literal=postgres-password=$(kubectl get secret postgresql-secret -n data -o jsonpath='{.data.postgres-password}' | base64 -d) \
     -n data
   ```

2. **develop 브랜치 확인**
   ```bash
   git checkout develop
   git pull origin develop
   ```

3. **root-app 배포 결정**
   - Option A: ArgoCD로 전환 (GitOps 활성화)
   - Option B: 현재 상태 유지 (Ansible 수동 배포)

### GitOps 전환 시 (Option A)

1. **root-app 배포**
   ```bash
   kubectl apply -f argocd/root-app.yaml
   ```

2. **동기화 확인**
   ```bash
   kubectl get applications -n argocd -w
   ```

3. **ApplicationSet 생성 확인**
   ```bash
   kubectl get applicationsets -n argocd
   ```

4. **API Services 배포 확인**
   ```bash
   kubectl get pods -n auth,character,chat,info,location,my,scan
   ```

### 현재 상태 유지 시 (Option B)

1. **API Services 수동 배포**
   ```bash
   kubectl apply -k k8s/overlays/auth
   kubectl apply -k k8s/overlays/character
   # ... (각 서비스별)
   ```

2. **Workers 배포**
   ```bash
   kubectl apply -f argocd/apps/apis/workers/celery-workers.yaml
   ```

---

## 🔧 권장 사항

### 1. GitOps 전환 강력 권장
**이유:**
- ✅ 코드베이스에 이미 완성된 ArgoCD 구조 존재
- ✅ App-of-Apps 패턴으로 체계적인 관리 가능
- ✅ 자동 동기화, Self-Heal 기능 활용 가능
- ✅ Wave 기반 순차 배포로 의존성 관리
- ✅ Atlantis와 연계하여 완전한 GitOps 파이프라인 구축 가능

**실행 방법:**
```bash
# 1. develop 브랜치로 전환
git checkout develop

# 2. root-app 배포
kubectl apply -f argocd/root-app.yaml

# 3. ArgoCD UI 접속 및 확인
# https://argocd.growbin.app
```

### 2. PostgreSQL Secret 즉시 수정
```bash
# Secret 복사
kubectl get secret postgresql-secret -n data -o yaml | \
  sed 's/postgresql-secret/postgres-secret/' | \
  kubectl apply -f -
```

### 3. develop 브랜치 통합 전략 수립
- main vs develop 브랜치 정책 명확화
- ArgoCD targetRevision 전략 결정
- CI/CD 파이프라인 브랜치 전략과 통일

---

## 📈 클러스터 리소스 현황

**노드:**
- Master: 1개
- Workers: 13개
- Storage 전용 노드: 1개 (k8s-worker-storage)

**스토리지:**
- StorageClass: gp3 (EBS CSI Driver)
- 총 PV 사용량: 130Gi

**네트워크:**
- CNI: Calico (추정)
- Ingress Controller: AWS ALB Controller
- LoadBalancer: ALB (단일 ALB 공유)

---

## 결론

**현재 상태:**
- 클러스터는 **정상 동작** 중
- 인프라 계층은 **대부분 구축** 완료
- ArgoCD는 설치되었으나 **사용되지 않음**
- API 서비스는 **배포 대기** 상태

**다음 단계:**
1. PostgreSQL Secret 수정 (즉시)
2. develop 브랜치 확인 및 전환
3. **GitOps 전환 여부 결정** (강력 권장: 전환)
4. root-app 배포로 전체 스택 활성화

**GitOps 전환 시 예상 효과:**
- ✅ 배포 자동화
- ✅ 인프라 as Code 완전 구현
- ✅ Drift 자동 감지 및 복구
- ✅ 선언적 배포 관리
- ✅ Atlantis 연계로 PR 기반 인프라 변경

---

**보고서 작성:** AI Assistant  
**기준 시각:** 2025-11-15 (현재)

