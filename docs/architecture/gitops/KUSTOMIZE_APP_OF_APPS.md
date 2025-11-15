# Kustomize + App of Apps 패턴 가이드

## ✅ 결론: 완벽하게 호환됩니다!

Kustomize와 App of Apps 패턴은 **최고의 조합**입니다.

```yaml
App of Apps: 구조 관리 (배포 순서, 의존성)
Kustomize:   컨텐츠 관리 (환경별 커스터마이징)
```

---

## 🎯 현재 프로젝트 구조

### 이미 Kustomize 사용 중!

```
k8s/
├── base/                        # 공통 리소스
│   ├── deployment.yaml
│   ├── service.yaml
│   └── kustomization.yaml
│
└── overlays/                    # 도메인별 커스터마이징
    ├── auth/
    │   ├── deployment-patch.yaml
    │   └── kustomization.yaml
    ├── my/
    ├── scan/
    ├── character/
    ├── location/
    ├── info/
    └── chat/
```

---

## 🚀 Kustomize + App of Apps 구현

### 현재: ApplicationSet 사용 중

```yaml
# argocd/applications/ecoeco-appset-kustomize.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ecoeco-api-services-kustomize
spec:
  generators:
    - list:
        elements:
          - domain: auth
          - domain: my
          - domain: scan
  
  template:
    spec:
      source:
        repoURL: https://github.com/SeSACTHON/backend
        path: k8s/overlays/{{domain}}  # ← Kustomize overlay
```

**이미 Kustomize + GitOps 사용 중!** ✅

---

## 💡 App of Apps 패턴으로 개선

### 현재 구조 (ApplicationSet)

```
┌─────────────────────────────────────────┐
│ ApplicationSet                           │
│ └─ ecoeco-api-services-kustomize        │
│    ├─ auth  (k8s/overlays/auth)         │
│    ├─ my    (k8s/overlays/my)           │
│    └─ scan  (k8s/overlays/scan)         │
└─────────────────────────────────────────┘
```

**문제점**:
- ❌ 배포 순서 제어 어려움 (모두 동시 배포)
- ❌ Infrastructure vs Application 구분 없음

### 개선: App of Apps 패턴

```
┌─────────────────────────────────────────────────────────┐
│ Root Application (App of Apps)                          │
│ └─ argocd/applications/ (전체 앱 관리)                  │
│                                                          │
│    ├─ Wave 0: Infrastructure App                        │
│    │  └─ k8s/infrastructure/ (Kustomize)               │
│    │     ├─ namespaces                                  │
│    │     ├─ networkpolicies                             │
│    │     └─ servicemonitors                             │
│    │                                                     │
│    ├─ Wave 1: Databases App                             │
│    │  └─ ApplicationSet → PostgreSQL, Redis, RabbitMQ │
│    │                                                     │
│    └─ Wave 2: API Services App                          │
│       └─ ApplicationSet → auth, my, scan, etc.         │
│          (각각 k8s/overlays/{domain} 사용)              │
└─────────────────────────────────────────────────────────┘
```

---

## 📂 디렉토리 구조 (제안)

```bash
backend/
├── argocd/
│   ├── root-app.yaml                    # App of Apps (최상위)
│   └── applications/
│       ├── infrastructure.yaml          # Wave 0 (Kustomize)
│       ├── databases.yaml               # Wave 1 (Kustomize)
│       ├── workers.yaml                 # Wave 2 (Kustomize)
│       └── api-services-appset.yaml     # Wave 3 (ApplicationSet + Kustomize)
│
└── k8s/
    ├── infrastructure/                  # Wave 0
    │   ├── namespaces/
    │   │   ├── domain-based.yaml
    │   │   └── kustomization.yaml
    │   ├── networkpolicies/
    │   │   ├── domain-isolation.yaml
    │   │   └── kustomization.yaml
    │   └── kustomization.yaml           # Infrastructure 통합
    │
    ├── databases/                       # Wave 1
    │   ├── postgresql/
    │   │   ├── statefulset.yaml
    │   │   └── kustomization.yaml
    │   ├── redis/
    │   └── rabbitmq/
    │
    ├── workers/                         # Wave 2
    │   ├── storage/
    │   │   └── kustomization.yaml
    │   └── ai/
    │       └── kustomization.yaml
    │
    ├── base/                            # API 공통 (Wave 3)
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   └── kustomization.yaml
    │
    └── overlays/                        # API 도메인별 (Wave 3)
        ├── auth/
        │   ├── deployment-patch.yaml
        │   └── kustomization.yaml
        ├── my/
        ├── scan/
        └── ...
```

---

## 🎨 구현 예시

### 1. Root Application (App of Apps)

```yaml
# argocd/root-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  project: default
  
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: argocd/applications  # 모든 하위 Application 정의
  
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### 2. Infrastructure Application (Kustomize)

```yaml
# argocd/applications/infrastructure.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infrastructure
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"  # 가장 먼저
spec:
  project: default
  
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: main
    path: k8s/infrastructure  # ← Kustomize 경로
  
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Infrastructure Kustomize**:

```yaml
# k8s/infrastructure/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespaces/domain-based.yaml
  - networkpolicies/domain-isolation.yaml
  - monitoring/servicemonitors-domain-ns.yaml
```

### 3. API Services ApplicationSet (Kustomize)

```yaml
# argocd/applications/api-services-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: api-services
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "3"  # Infrastructure 다음
spec:
  generators:
    - list:
        elements:
          - domain: auth
            phase: "1"
          - domain: my
            phase: "1"
          - domain: scan
            phase: "2"
          # ... more APIs
  
  template:
    metadata:
      name: 'api-{{domain}}'
    spec:
      project: default
      
      source:
        repoURL: https://github.com/SeSACTHON/backend
        targetRevision: main
        path: k8s/overlays/{{domain}}  # ← Kustomize overlay
      
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{domain}}'  # 도메인별 네임스페이스
      
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

---

## 🔄 배포 흐름

### 완벽한 GitOps + Kustomize

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 개발자가 코드 변경                                         │
│    git commit -m "feat: auth API 업데이트"                   │
│    git push origin main                                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. ArgoCD가 변경 감지 (매 3분)                               │
│    git diff k8s/overlays/auth/*                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Kustomize 빌드                                           │
│    kubectl kustomize k8s/overlays/auth/                     │
│    → 최종 YAML 생성                                          │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Kubernetes에 적용                                         │
│    kubectl apply -f rendered.yaml                           │
│    → auth-api Deployment 업데이트                            │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ 장점 정리

### App of Apps + Kustomize 조합

| 기능 | App of Apps | Kustomize | 조합 효과 |
|------|------------|-----------|----------|
| **배포 순서** | ✅ Sync Wave | - | 의존성 관리 |
| **환경별 설정** | - | ✅ Overlay | dev/staging/prod |
| **코드 재사용** | - | ✅ Base | DRY 원칙 |
| **구조 관리** | ✅ 계층 구조 | - | 대규모 프로젝트 |
| **명확성** | ✅ | ✅ | 순수 YAML |
| **디버깅** | ✅ | ✅ | 쉬움 |

---

## 🚀 마이그레이션 가이드

### Step 1: Infrastructure Kustomize 생성

```bash
mkdir -p k8s/infrastructure/{namespaces,networkpolicies}

# Kustomization 생성
cat > k8s/infrastructure/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - namespaces/domain-based.yaml
  - networkpolicies/domain-isolation.yaml
EOF
```

### Step 2: Root Application 생성

```bash
kubectl apply -f argocd/root-app.yaml
```

### Step 3: 하위 Applications 생성

```bash
kubectl apply -f argocd/applications/infrastructure.yaml
kubectl apply -f argocd/applications/api-services-appset.yaml
```

### Step 4: 동기화 확인

```bash
# Root App 상태
argocd app get root-app

# 하위 Apps 상태
argocd app list
```

---

## 📊 현재 vs 개선 비교

### 현재 (ApplicationSet만)

```
✅ 장점:
  - Kustomize 사용 중
  - 도메인별 독립 배포

❌ 단점:
  - 배포 순서 제어 어려움
  - Infrastructure와 Application 구분 없음
  - 전체 구조 파악 어려움
```

### 개선 (App of Apps + Kustomize)

```
✅ 장점:
  - 명확한 계층 구조
  - Sync Wave로 배포 순서 제어
  - Infrastructure / Application 명확히 분리
  - 대규모 확장 용이
  - 전체 구조 한눈에 파악

단점 없음! ⭐
```

---

## 🎯 권장사항

### 현재 프로젝트에 적용

1. **Infrastructure Kustomize 정리** (2-3일)
   ```
   k8s/infrastructure/ 생성
   └─ namespaces, networkpolicies 이동
   ```

2. **Root Application 생성** (1일)
   ```
   argocd/root-app.yaml 작성
   ```

3. **하위 Applications 정리** (1일)
   ```
   argocd/applications/ 구조화
   └─ infrastructure, databases, apis
   ```

4. **테스트 및 배포** (1-2일)

**총 소요 시간: 약 1주일**

---

## 📚 참고 자료

- [ArgoCD App of Apps](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/)
- [Kustomize Official](https://kustomize.io/)
- [ArgoCD + Kustomize Integration](https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/)
- [Sync Waves and Phases](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/)

---

**작성일**: 2025-11-14  
**상태**: Kustomize + App of Apps 패턴 완벽 호환 확인 ✅  
**다음**: 프로젝트에 App of Apps 패턴 적용

