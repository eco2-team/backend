# GitOps 파이프라인 구조 (Kustomize + ArgoCD)

**문서 버전**: v0.8.0  
**최종 업데이트**: 2025-11-11  
**참고 문서**:
- [ArgoCD Official Docs](https://argo-cd.readthedocs.io/)
- [Kustomize Official Docs](https://kubectl.docs.kubernetes.io/)
- [ArgoCD ApplicationSet](https://argo-cd.readthedocs.io/en/stable/user-guide/application-set/)

---

## 🎯 GitOps 파이프라인 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitOps Flow                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Developer          Git Repository         ArgoCD         K8s   │
│     │                    │                   │            │     │
│     │ 1. Code Change     │                   │            │     │
│     ├───────────────────>│                   │            │     │
│     │                    │                   │            │     │
│     │ 2. Update Manifest │                   │            │     │
│     ├───────────────────>│                   │            │     │
│     │   (k8s/overlays)   │                   │            │     │
│     │                    │                   │            │     │
│     │                    │ 3. Poll/Webhook   │            │     │
│     │                    ├──────────────────>│            │     │
│     │                    │                   │            │     │
│     │                    │ 4. Git Pull       │            │     │
│     │                    │<──────────────────┤            │     │
│     │                    │                   │            │     │
│     │                    │                   │ 5. Render  │     │
│     │                    │                   │  Kustomize │     │
│     │                    │                   ├────────┐   │     │
│     │                    │                   │        │   │     │
│     │                    │                   │<───────┘   │     │
│     │                    │                   │            │     │
│     │                    │                   │ 6. Apply   │     │
│     │                    │                   ├───────────>│     │
│     │                    │                   │            │     │
│     │                    │                   │ 7. Health  │     │
│     │                    │                   │   Check    │     │
│     │                    │                   │<───────────┤     │
│     │                    │                   │            │     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ 전체 아키텍처

### Layer 1: Source Control (GitHub)

```
backend/
├── services/                    # Application Source Code
│   ├── auth/
│   ├── my/
│   ├── scan/
│   └── ...
│
├── k8s/                         # Kubernetes Manifests (GitOps)
│   ├── base/                    # 공통 템플릿
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   │
│   └── overlays/                # 환경/서비스별 커스터마이징
│       ├── auth/
│       │   ├── deployment-patch.yaml
│       │   └── kustomization.yaml
│       ├── my/
│       ├── scan/
│       └── ...
│
├── argocd/                      # ArgoCD Applications
│   └── applications/
│       └── ecoeco-appset-kustomize.yaml
│
└── .github/workflows/           # CI Pipeline
    └── api-build.yml
```

### Layer 2: CI Pipeline (GitHub Actions)

**참고**: [GitHub Actions Documentation](https://docs.github.com/en/actions)

```yaml
# .github/workflows/api-build.yml
name: Build and Push API Images

on:
  push:
    branches: [main]
    paths: ['services/**']

jobs:
  build-auth-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./services/auth
          push: true
          tags: ghcr.io/sesacthon/auth:latest
```

**Flow**:
1. Developer pushes code to `services/auth/`
2. GitHub Actions detects change
3. Build Docker image
4. Push to GHCR: `ghcr.io/sesacthon/auth:latest`

### Layer 3: CD Pipeline (ArgoCD + Kustomize)

**참고**: 
- [ArgoCD Core Concepts](https://argo-cd.readthedocs.io/en/stable/core_concepts/)
- [Kustomize with ArgoCD](https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/)

#### 3.1 ApplicationSet

**참고**: [ApplicationSet Documentation](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/)

```yaml
# argocd/applications/ecoeco-appset-kustomize.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ecoeco-api-services-kustomize
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - domain: auth
            namespace: api
            phase: "1"
          # ... more APIs
  
  template:
    metadata:
      name: 'ecoeco-api-{{domain}}'
    spec:
      project: default
      source:
        repoURL: https://github.com/SeSACTHON/backend
        targetRevision: main
        path: k8s/overlays/{{domain}}  # Kustomize overlay
      
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{namespace}}'
      
      syncPolicy:
        automated:
          prune: true      # 삭제된 리소스 자동 제거
          selfHeal: true   # Git 상태로 자동 복구
```

**동작 원리**:
1. ApplicationSet이 `list` generator를 통해 7개 Application 생성
2. 각 Application은 `k8s/overlays/{domain}` 경로를 참조
3. ArgoCD가 Kustomize를 자동으로 렌더링

#### 3.2 Kustomize Structure

**참고**: [Kustomize Introduction](https://kubectl.docs.kubernetes.io/guides/introduction/)

```
k8s/
├── base/                        # 공통 리소스
│   ├── deployment.yaml          # 기본 Deployment 템플릿
│   ├── service.yaml             # 기본 Service 템플릿
│   └── kustomization.yaml       # Base 정의
│
└── overlays/
    └── auth/                    # Auth API 커스터마이징
        ├── deployment-patch.yaml    # Auth 전용 설정
        └── kustomization.yaml       # Overlay 정의
```

**Base (k8s/base/kustomization.yaml)**:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
```

**Overlay (k8s/overlays/auth/kustomization.yaml)**:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: api
namePrefix: auth-      # 리소스 이름에 prefix 추가

resources:
  - ../../base         # Base manifests 상속

images:
  - name: ghcr.io/sesacthon/placeholder
    newName: ghcr.io/sesacthon/auth     # 이미지 교체
    newTag: latest

patches:
  - path: deployment-patch.yaml   # 부분 수정

commonLabels:
  domain: auth
  phase: "1"
```

**참고**: [Kustomize Patching](https://kubectl.docs.kubernetes.io/references/kustomize/patches/)

#### 3.3 ArgoCD Sync Process

**참고**: [ArgoCD Sync Phases](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-phases/)

```
1. Git Repository Poll/Webhook
   ↓
2. Fetch Latest Commit
   ↓
3. Render Manifests (Kustomize Build)
   $ kubectl kustomize k8s/overlays/auth/
   ↓
4. Compare with Cluster State (Diff)
   ↓
5. Sync (Apply Changes)
   $ kubectl apply -f <rendered-manifests>
   ↓
6. Health Check
   - Deployment: replicas ready?
   - Service: endpoints available?
   ↓
7. Update Application Status
   - Synced / OutOfSync
   - Healthy / Degraded / Progressing
```

---

## 🔄 GitOps Workflow 시나리오

### 시나리오 1: 새로운 기능 배포

```bash
# 1. Developer: 코드 변경
$ cd services/auth/
$ vim app/main.py  # 새 기능 추가

# 2. Developer: 이미지 빌드 트리거 (자동)
$ git add .
$ git commit -m "feat: Add new authentication feature"
$ git push origin main

# → GitHub Actions: 자동 빌드
#   ✓ Build Docker image
#   ✓ Push to ghcr.io/sesacthon/auth:latest

# 3. Developer: Manifest 업데이트 (필요시)
$ cd k8s/overlays/auth/
$ vim deployment-patch.yaml  # 환경 변수 추가
$ git commit -m "config: Add new env var for auth"
$ git push origin main

# 4. ArgoCD: 자동 감지 및 배포
#   ✓ Detect Git change
#   ✓ Render Kustomize
#   ✓ Apply to cluster
#   ✓ Health check

# 5. 배포 완료!
$ kubectl get pods -n api | grep auth
auth-api-xxx   1/1   Running   0   30s
```

### 시나리오 2: Replica 수 변경

```bash
# 1. Developer: Overlay patch 수정
$ cd k8s/overlays/auth/
$ vim deployment-patch.yaml

# Before:
spec:
  replicas: 2

# After:
spec:
  replicas: 4

$ git commit -m "scale: Increase auth replicas to 4"
$ git push origin main

# 2. ArgoCD: 자동 적용
#   ✓ Detect change
#   ✓ Update Deployment
#   ✓ Scale to 4 replicas

# 3. 확인
$ kubectl get deployment auth-api -n api
NAME       READY   UP-TO-DATE   AVAILABLE
auth-api   4/4     4            4
```

### 시나리오 3: 롤백

**참고**: [ArgoCD Rollback](https://argo-cd.readthedocs.io/en/stable/user-guide/history/)

```bash
# 1. 문제 발견
$ kubectl get pods -n api | grep auth
auth-api-xxx   0/1   CrashLoopBackOff   5   5m

# 2. ArgoCD에서 이전 버전으로 롤백
$ kubectl patch application ecoeco-api-auth -n argocd \
  --type merge -p '{"spec":{"source":{"targetRevision":"<previous-commit>"}}}'

# 또는 Git에서 revert
$ git revert HEAD
$ git push origin main

# 3. ArgoCD 자동 재배포
#   ✓ Apply previous state
#   ✓ Pods restart with old image

# 4. 복구 완료
$ kubectl get pods -n api | grep auth
auth-api-xxx   1/1   Running   0   30s
```

---

## 🔧 ArgoCD 설정

### Auto-Sync 설정

**참고**: [ArgoCD Sync Policy](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/)

```yaml
syncPolicy:
  automated:
    prune: true      # Git에서 삭제된 리소스 자동 삭제
    selfHeal: true   # Cluster의 수동 변경 자동 복구
    allowEmpty: false # 빈 commit 무시
  
  syncOptions:
    - CreateNamespace=true    # Namespace 자동 생성
    - PrunePropagationPolicy=foreground  # 순서 보장
    - PruneLast=true          # 생성 후 삭제
  
  retry:
    limit: 3
    backoff:
      duration: 5s
      factor: 2
      maxDuration: 1m
```

### Sync Waves (배포 순서 제어)

**참고**: [ArgoCD Sync Waves](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-waves/)

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "1"  # Phase 1 먼저
```

**배포 순서**:
```
Wave 0: Infrastructure (PostgreSQL, Redis, RabbitMQ)
  ↓
Wave 1: Phase 1 APIs (auth, my, scan)
  ↓
Wave 2: Phase 2 APIs (character, location)
  ↓
Wave 3: Phase 3 APIs (info, chat)
  ↓
Wave 4: Workers (storage, ai)
```

---

## 📊 GitOps vs Traditional CD 비교

| 측면 | Traditional CD | GitOps (ArgoCD + Kustomize) |
|------|---------------|----------------------------|
| **배포 트리거** | CI Pipeline (push) | Git Commit (pull) |
| **상태 관리** | CI tool에서 관리 | Git이 Single Source of Truth |
| **롤백** | 이전 빌드 재실행 | Git revert |
| **Drift 감지** | 없음 | ✅ Auto-detection |
| **멀티 클러스터** | 복잡 | ✅ ApplicationSet으로 간단 |
| **보안** | CI가 cluster 접근 | ✅ Pull model (cluster가 git 접근) |
| **감사 추적** | CI logs | ✅ Git history |

---

## 🎓 Kustomize 핵심 개념

### 1. Resources
**참고**: [Kustomize Resources](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/resource/)

```yaml
resources:
  - deployment.yaml
  - service.yaml
  - ../../base         # 다른 kustomization 참조
```

### 2. Patches
**참고**: [Kustomize Patches](https://kubectl.docs.kubernetes.io/references/kustomize/patches/)

```yaml
patches:
  - path: deployment-patch.yaml  # Strategic Merge Patch
  
  # 또는 inline patch
  - target:
      kind: Deployment
      name: api
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 4
```

### 3. Images
**참고**: [Kustomize Images](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/images/)

```yaml
images:
  - name: placeholder-image
    newName: ghcr.io/sesacthon/auth
    newTag: v1.2.3
```

### 4. NamePrefix/Suffix
**참고**: [Kustomize Name Transformers](https://kubectl.docs.kubernetes.io/references/kustomize/nameprefix/)

```yaml
namePrefix: auth-      # auth-api, auth-service
nameSuffix: -v2        # api-v2, service-v2
```

### 5. CommonLabels
**참고**: [Kustomize Labels](https://kubectl.docs.kubernetes.io/references/kustomize/commonlabels/)

```yaml
commonLabels:
  app: my-app
  environment: production
  domain: auth
```

---

## 🔍 디버깅 및 검증

### 로컬에서 Kustomize 출력 확인

```bash
# Kustomize 결과 미리보기
$ kubectl kustomize k8s/overlays/auth/

# 특정 리소스만 확인
$ kubectl kustomize k8s/overlays/auth/ | grep -A 20 "kind: Deployment"

# Diff 확인 (dry-run)
$ kubectl kustomize k8s/overlays/auth/ | kubectl diff -f -
```

### ArgoCD에서 상태 확인

**참고**: [ArgoCD CLI](https://argo-cd.readthedocs.io/en/stable/user-guide/commands/argocd/)

```bash
# Application 목록
$ kubectl get applications -n argocd

# 특정 Application 상세
$ kubectl get application ecoeco-api-auth -n argocd -o yaml

# Sync 상태
$ kubectl get application ecoeco-api-auth -n argocd \
  -o jsonpath='{.status.sync.status}'

# Health 상태
$ kubectl get application ecoeco-api-auth -n argocd \
  -o jsonpath='{.status.health.status}'
```

### 에러 디버깅

```bash
# Application conditions 확인
$ kubectl get application ecoeco-api-auth -n argocd \
  -o jsonpath='{.status.conditions}'

# ArgoCD repo-server 로그
$ kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server

# ArgoCD application-controller 로그
$ kubectl logs -n argocd -l app.kubernetes.io/name=argocd-application-controller
```

---

## 📚 참고 자료

### ArgoCD 공식 문서
- **Core Concepts**: https://argo-cd.readthedocs.io/en/stable/core_concepts/
- **ApplicationSet**: https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/
- **Sync Options**: https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/
- **Auto-Sync**: https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/

### Kustomize 공식 문서
- **Introduction**: https://kubectl.docs.kubernetes.io/guides/introduction/
- **Kustomization File**: https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/
- **Patches**: https://kubectl.docs.kubernetes.io/references/kustomize/patches/
- **Examples**: https://github.com/kubernetes-sigs/kustomize/tree/master/examples

### Best Practices
- **GitOps Principles**: https://opengitops.dev/
- **ArgoCD Best Practices**: https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/
- **Kustomize Best Practices**: https://kubectl.docs.kubernetes.io/guides/config_management/

---

## 📝 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-11-11 | v0.8.0 | Kustomize + ArgoCD GitOps 파이프라인 구조 문서화 |

