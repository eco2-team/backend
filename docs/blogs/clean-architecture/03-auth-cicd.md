# 이코에코(Eco²) Clean Architecture #3: Auth - CI/CD

리팩토링된 코드를 안전하게 배포하기 위한 CI/CD 파이프라인 구성.

---

## 배포 전략: Canary

Clean Architecture로 리팩토링된 코드를 프로덕션에 바로 배포하는 것은 위험하다.
Canary 배포로 일부 트래픽만 새 버전으로 라우팅하여 검증한다.

### 개념

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Istio Gateway                              │
├─────────────────────────────────────────────────────────────────────────┤
│                           VirtualService                                │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │  Request Headers                                              │     │
│   │                                                               │     │
│   │  X-Canary: true  ────────────→  auth-api-canary (v2)         │     │
│   │                                  - Clean Architecture         │     │
│   │                                  - New OAuth flow             │     │
│   │                                                               │     │
│   │  (default)       ────────────→  auth-api (v1)                │     │
│   │                                  - Legacy code                │     │
│   │                                  - Stable                     │     │
│   └──────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 장점

| 항목 | 설명 |
|------|------|
| **위험 최소화** | 문제 발생 시 Canary Pod만 영향 |
| **점진적 검증** | 실 트래픽으로 검증 가능 |
| **빠른 롤백** | Canary Pod 스케일 다운으로 즉시 롤백 |
| **A/B 테스트** | 헤더 기반으로 특정 사용자만 테스트 가능 |

---

## Kubernetes Manifest 구조

```
workloads/domains/auth/
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml          # Stable (v1)
│   ├── deployment-canary.yaml   # Canary (v2)
│   ├── service.yaml             # 공통 Service
│   ├── configmap.yaml
│   └── destination-rule.yaml    # Istio 서브셋 정의
├── dev/
│   ├── kustomization.yaml
│   └── patch-deployment.yaml
└── prod/
    └── kustomization.yaml

workloads/domains/auth-relay/     # Worker
├── base/
│   ├── kustomization.yaml
│   ├── deployment.yaml          # Stable
│   ├── deployment-canary.yaml   # Canary
│   └── service.yaml
└── dev/
    └── kustomization.yaml
```

### Stable Deployment

```yaml
# workloads/domains/auth/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-api
  namespace: auth
  labels:
    app: auth-api
    version: v1              # Stable 버전
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth-api
      version: v1
  template:
    metadata:
      labels:
        app: auth-api
        version: v1
    spec:
      containers:
      - name: auth-api
        image: docker.io/mng990/eco2:auth-api-dev-latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: auth-config
        - secretRef:
            name: auth-secret
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Canary Deployment

```yaml
# workloads/domains/auth/base/deployment-canary.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-api-canary
  namespace: auth
  labels:
    app: auth-api
    version: v2              # Canary 버전
    release: canary
spec:
  replicas: 1                # 최소 리플리카
  selector:
    matchLabels:
      app: auth-api
      version: v2
  template:
    metadata:
      labels:
        app: auth-api
        version: v2
        release: canary
    spec:
      containers:
      - name: auth-api
        image: docker.io/mng990/eco2:auth-api-dev-canary
        ports:
        - containerPort: 8000
        env:
        - name: RELEASE_TYPE
          value: canary       # Canary 식별용
        envFrom:
        - configMapRef:
            name: auth-config
        - secretRef:
            name: auth-secret
```

### Istio DestinationRule

```yaml
# workloads/domains/auth/base/destination-rule.yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: auth-api
  namespace: auth
spec:
  host: auth-api
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
```

### Istio VirtualService

```yaml
# workloads/ingress/istio/auth-virtualservice.yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: auth-api
  namespace: auth
spec:
  hosts:
  - auth-api
  http:
  # Canary 라우팅 (헤더 기반)
  - match:
    - headers:
        x-canary:
          exact: "true"
    route:
    - destination:
        host: auth-api
        subset: v2
        port:
          number: 8000
  # 기본 라우팅 (Stable)
  - route:
    - destination:
        host: auth-api
        subset: v1
        port:
          number: 8000
```

---

## Worker 배포 (auth-relay)

### Worker 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Auth Relay Worker                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Redis Outbox                     RabbitMQ                             │
│   ┌─────────┐                     ┌─────────┐                          │
│   │  List   │  ─── Consume ────→  │  Queue  │                          │
│   │ outbox  │                     │blacklist│                          │
│   └─────────┘                     └─────────┘                          │
│                                        │                                │
│                                        ↓                                │
│                                   Other Nodes                           │
│                                  (Token Sync)                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Worker Deployment

```yaml
# workloads/domains/auth-relay/base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-relay
  namespace: auth
  labels:
    app: auth-relay
    version: v1
spec:
  replicas: 1
  selector:
    matchLabels:
      app: auth-relay
      version: v1
  template:
    metadata:
      labels:
        app: auth-relay
        version: v1
    spec:
      containers:
      - name: auth-relay
        image: docker.io/mng990/eco2:auth-relay-dev-latest
        envFrom:
        - configMapRef:
            name: auth-relay-config
        - secretRef:
            name: auth-relay-secret
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
```

### Worker Canary Deployment

```yaml
# workloads/domains/auth-relay/base/deployment-canary.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-relay-canary
  namespace: auth
  labels:
    app: auth-relay
    version: v2
    release: canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: auth-relay
      version: v2
  template:
    metadata:
      labels:
        app: auth-relay
        version: v2
        release: canary
    spec:
      containers:
      - name: auth-relay
        image: docker.io/mng990/eco2:auth-relay-dev-canary
        env:
        - name: RELEASE_TYPE
          value: canary
        envFrom:
        - configMapRef:
            name: auth-relay-config
        - secretRef:
            name: auth-relay-secret
```

---

## CI/CD 파이프라인

### 전체 플로우

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CI/CD Pipeline Flow                           │
└─────────────────────────────────────────────────────────────────────────┘

 Developer        GitHub Actions           Docker Hub           Kubernetes
     │                  │                      │                     │
     │  1. Push to      │                      │                     │
     │     develop      │                      │                     │
     │─────────────────→│                      │                     │
     │                  │                      │                     │
     │                  │  2. Detect changes   │                     │
     │                  │     apps/auth/**     │                     │
     │                  │                      │                     │
     │                  │  3. Run tests        │                     │
     │                  │     pytest           │                     │
     │                  │                      │                     │
     │                  │  4. Build Docker     │                     │
     │                  │─────────────────────→│                     │
     │                  │                      │                     │
     │                  │  5. Push image       │                     │
     │                  │   auth-api-dev-latest│                     │
     │                  │─────────────────────→│                     │
     │                  │                      │                     │
     │                  │                      │  6. ArgoCD detects  │
     │                  │                      │     digest change   │
     │                  │                      │────────────────────→│
     │                  │                      │                     │
     │                  │                      │  7. Sync manifests  │
     │                  │                      │────────────────────→│
     │                  │                      │                     │
     │                  │                      │  8. Rolling update  │
     │                  │                      │                     │
     │←────────────────────────────────────────────────────────────── │
     │                       9. Deployment complete                   │
     │                                                                │
```

### 경로 감지 (apps/ + domains/)

기존 `domains/auth/`와 새로운 `apps/auth/` 모두 지원:

```yaml
# .github/workflows/ci-services.yml
name: CI - API Services

on:
  push:
    branches: [develop, main]
    paths:
      - "apps/**"           # Clean Architecture
      - "domains/**"        # Legacy
      - ".github/workflows/ci-services.yml"

env:
  API_SERVICES: "auth,character,chat,info,location,my,scan"
```

### 서비스 감지 로직

```python
# Python pseudo-code for detection logic
def detect_changed_services(changed_files: list[str]) -> set[str]:
    services = set()
    
    for path in changed_files:
        parts = path.split("/")
        
        # apps/<service>/ 경로 감지 (Clean Architecture)
        if len(parts) >= 2 and parts[0] == "apps":
            service = parts[1]
            if service in API_SERVICES:
                services.add(service)
        
        # domains/<service>/ 경로 감지 (Legacy)
        elif len(parts) >= 2 and parts[0] == "domains":
            service = parts[1]
            # _shared, _base 제외
            if service in API_SERVICES and not service.startswith("_"):
                services.add(service)
    
    return services
```

### Dockerfile 자동 감지

```yaml
# .github/workflows/ci-services.yml
jobs:
  api-build:
    steps:
      - name: Determine Dockerfile path
        id: dockerfile
        run: |
          SERVICE="${{ matrix.service }}"
          
          # Clean Architecture 버전 우선
          if [ -f "apps/${SERVICE}/Dockerfile" ]; then
            echo "path=apps/${SERVICE}/Dockerfile" >> "$GITHUB_OUTPUT"
            echo "source=apps/${SERVICE}" >> "$GITHUB_OUTPUT"
          else
            echo "path=domains/${SERVICE}/Dockerfile" >> "$GITHUB_OUTPUT"
            echo "source=domains/${SERVICE}" >> "$GITHUB_OUTPUT"
          fi

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ${{ steps.dockerfile.outputs.path }}
          push: true
          tags: |
            ${{ env.IMAGE_REPO }}:${{ matrix.service }}-api-dev-latest
            ${{ env.IMAGE_REPO }}:${{ matrix.service }}-api-dev-${{ github.sha }}
```

### PYTHONPATH 설정

Clean Architecture 구조에서는 `apps/` 디렉토리를 PYTHONPATH에 포함해야 한다.

```yaml
# .github/workflows/ci-services.yml
      - name: Determine source path
        id: source
        run: |
          SERVICE="${{ matrix.service }}"
          
          if [ -d "apps/${SERVICE}" ]; then
            echo "path=apps/${SERVICE}" >> "$GITHUB_OUTPUT"
            # Clean Architecture: 프로젝트 루트를 PYTHONPATH에
            echo "pythonpath=${{ github.workspace }}" >> "$GITHUB_OUTPUT"
          else
            echo "path=domains/${SERVICE}" >> "$GITHUB_OUTPUT"
            # Legacy: 서비스 디렉토리를 PYTHONPATH에
            echo "pythonpath=${{ github.workspace }}/domains/${SERVICE}" >> "$GITHUB_OUTPUT"
          fi

      - name: Run tests
        working-directory: ${{ steps.source.outputs.path }}
        env:
          PYTHONPATH: ${{ steps.source.outputs.pythonpath }}
        run: |
          pytest tests/ -v --tb=short
```

---

## Canary 빌드 워크플로우

PR에 `canary` 라벨 추가 시 Canary 이미지 자동 빌드.

```yaml
# .github/workflows/ci-canary.yml
name: CI - Canary Build

on:
  pull_request:
    types: [labeled, synchronize]

jobs:
  check-canary-label:
    runs-on: ubuntu-latest
    outputs:
      is_canary: ${{ steps.check.outputs.is_canary }}
    steps:
      - name: Check for canary label
        id: check
        run: |
          PR_LABELS='${{ toJson(github.event.pull_request.labels.*.name) }}'
          if echo "$PR_LABELS" | jq -e 'contains(["canary"])' > /dev/null; then
            echo "is_canary=true" >> "$GITHUB_OUTPUT"
          else
            echo "is_canary=false" >> "$GITHUB_OUTPUT"
          fi

  api-canary-build:
    needs: check-canary-label
    if: needs.check-canary-label.outputs.is_canary == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [auth]  # Canary 대상 서비스
    steps:
      - uses: actions/checkout@v4

      - name: Prepare canary tags
        id: tags
        run: |
          CANARY_TAG="${{ matrix.service }}-api-dev-canary"
          SHA_TAG="${{ matrix.service }}-api-dev-canary-${{ github.sha }}"
          echo "tags=${{ env.IMAGE_REPO }}:${CANARY_TAG},${{ env.IMAGE_REPO }}:${SHA_TAG}" >> "$GITHUB_OUTPUT"

      - name: Build and push canary image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: apps/${{ matrix.service }}/Dockerfile
          push: true
          tags: ${{ steps.tags.outputs.tags }}
```

---

## Worker 빌드 워크플로우

```yaml
# .github/workflows/ci-auth-relay.yml
name: CI - Auth Relay Worker

on:
  push:
    branches: [develop, main]
    paths:
      - "apps/auth/workers/**"
      - "apps/auth/infrastructure/persistence_redis/**"
      - "apps/auth/Dockerfile.relay"

jobs:
  build-auth-relay:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: apps/auth/Dockerfile.relay
          push: true
          tags: |
            mng990/eco2:auth-relay-dev-latest
            mng990/eco2:auth-relay-dev-${{ github.sha }}
```

---

## ArgoCD GitOps 연동

### ApplicationSet

```yaml
# clusters/dev/apps/40-apis-appset.yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: dev-apis
  namespace: argocd
spec:
  generators:
  - list:
      elements:
      - name: auth
        phase: "1"
      - name: character
        phase: "2"
      # ... 기타 서비스
  template:
    metadata:
      name: dev-api-{{name}}
      annotations:
        # ArgoCD Image Updater - digest 변경 감지
        argocd-image-updater.argoproj.io/image-list: |
          stable=docker.io/mng990/eco2:{{name}}-api-dev-latest
        argocd-image-updater.argoproj.io/stable.update-strategy: digest
    spec:
      project: dev
      source:
        repoURL: https://github.com/eco2-team/backend.git
        targetRevision: develop
        path: workloads/domains/{{name}}/dev
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{name}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

### 배포 플로우 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ArgoCD GitOps Flow                                 │
└─────────────────────────────────────────────────────────────────────────┘

 GitHub               Docker Hub            ArgoCD              Kubernetes
    │                     │                   │                     │
    │  1. Push to         │                   │                     │
    │     develop         │                   │                     │
    │────────────────────→│                   │                     │
    │                     │                   │                     │
    │  2. CI builds &     │                   │                     │
    │     pushes image    │                   │                     │
    │                     │                   │                     │
    │                     │  3. Image Updater │                     │
    │                     │     detects new   │                     │
    │                     │     digest        │                     │
    │                     │──────────────────→│                     │
    │                     │                   │                     │
    │                     │                   │  4. Update image    │
    │                     │                   │     in deployment   │
    │                     │                   │────────────────────→│
    │                     │                   │                     │
    │                     │                   │  5. Rolling update  │
    │                     │                   │                     │
    │                     │                   │  6. Health check    │
    │                     │                   │←────────────────────│
    │                     │                   │                     │
    │                     │                   │  7. Sync complete   │
    │                     │                   │                     │
```

---

## Canary 테스트 방법

### 헤더 기반 라우팅

```bash
# Canary 버전 요청
curl -H "X-Canary: true" \
  https://api.growbin.app/api/v1/auth/health

# Stable 버전 요청 (기본)
curl https://api.growbin.app/api/v1/auth/health
```

### Pod 확인

```bash
# Stable Pod
kubectl get pods -n auth -l version=v1 -o wide

# Canary Pod
kubectl get pods -n auth -l version=v2 -o wide

# 로그 비교
kubectl logs -n auth -l version=v2 --tail=100 -f

# 두 버전 동시 로그 확인
kubectl logs -n auth -l app=auth-api --all-containers --tail=50
```

### 메트릭 비교

```bash
# Prometheus 쿼리 (예시)
# Canary 에러율
rate(http_requests_total{app="auth-api",version="v2",status=~"5.."}[5m])
/
rate(http_requests_total{app="auth-api",version="v2"}[5m])

# Stable 에러율과 비교
rate(http_requests_total{app="auth-api",version="v1",status=~"5.."}[5m])
/
rate(http_requests_total{app="auth-api",version="v1"}[5m])
```

---

## 롤백 전략

### Canary 문제 발생 시

```bash
# 방법 1: Canary Deployment 스케일 다운
kubectl scale deployment auth-api-canary -n auth --replicas=0

# 방법 2: Canary Deployment 삭제
kubectl delete deployment auth-api-canary -n auth

# 방법 3: Canary 라벨 제거 (CI에서 빌드 중단)
# PR에서 'canary' 라벨 제거
```

### ArgoCD Rollback

```bash
# Application 히스토리 확인
argocd app history dev-api-auth

# 특정 리비전으로 롤백
argocd app rollback dev-api-auth <REVISION>

# 또는 kubectl로 직접
kubectl rollout undo deployment/auth-api -n auth
```

### 긴급 롤백 스크립트

```bash
#!/bin/bash
# scripts/rollback-canary.sh

SERVICE=$1
NAMESPACE=${SERVICE}

echo "Rolling back ${SERVICE} canary deployment..."

# Canary 스케일 다운
kubectl scale deployment ${SERVICE}-api-canary -n ${NAMESPACE} --replicas=0

# 로그 확인
kubectl get pods -n ${NAMESPACE} -l version=v2

echo "Canary rollback complete. Stable version is serving all traffic."
```

---

## 트러블슈팅

### Docker Hub Rate Limit

```
Error: 429 Too Many Requests
toomanyrequests: You have reached your pull rate limit
```

**해결:**
1. Docker Hub 유료 계정 전환
2. GitHub Secrets에 새 토큰 등록
3. `DOCKERHUB_TOKEN` 업데이트

### ArgoCD Out of Sync

```bash
# Hard refresh
kubectl -n argocd annotate application dev-api-auth \
  argocd.argoproj.io/refresh=hard --overwrite

# Force sync
argocd app sync dev-api-auth --force --prune

# 또는 UI에서 "Sync" 버튼 클릭
```

### Image Pull 실패

```bash
# Secret 확인
kubectl get secret dockerhub-secret -n auth -o yaml

# Pod events 확인
kubectl describe pod -n auth -l app=auth-api | grep -A 10 Events

# 이미지 태그 확인
kubectl get deployment auth-api -n auth -o jsonpath='{.spec.template.spec.containers[0].image}'
```

---

## 파이프라인 요약

### 워크플로우

| 워크플로우 | 트리거 | 결과물 | 용도 |
|-----------|--------|--------|------|
| `ci-services.yml` | push to develop | `auth-api-dev-latest` | Stable 배포 |
| `ci-canary.yml` | PR + canary label | `auth-api-dev-canary` | Canary 테스트 |
| `ci-auth-relay.yml` | workers 변경 | `auth-relay-dev-latest` | Worker 배포 |

### 매니페스트

| 매니페스트 | 이미지 태그 | 버전 | 트래픽 |
|-----------|------------|------|--------|
| `deployment.yaml` | `auth-api-dev-latest` | v1 (stable) | 기본 |
| `deployment-canary.yaml` | `auth-api-dev-canary` | v2 (canary) | X-Canary: true |

### 체크리스트

- [ ] `apps/auth/Dockerfile` 존재 확인
- [ ] `apps/auth/Dockerfile.relay` 존재 확인
- [ ] CI 워크플로우 경로 감지 정상
- [ ] Docker Hub 토큰 유효
- [ ] ArgoCD Application 생성
- [ ] Istio VirtualService 설정
- [ ] 헤더 기반 라우팅 테스트

---

## 참고 자료

- [Istio Traffic Management](https://istio.io/latest/docs/concepts/traffic-management/)
- [ArgoCD Image Updater](https://argocd-image-updater.readthedocs.io/)
- [Canary Deployments on Kubernetes](https://kubernetes.io/docs/concepts/cluster-administration/manage-deployment/#canary-deployments)
- [GitHub Actions Docker Build](https://github.com/docker/build-push-action)
