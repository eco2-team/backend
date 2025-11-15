# App of Apps 재구성 의사결정

## 배경
- Terraform + Ansible로 **인프라 계층**은 일괄 구축되지만, 애플리케이션 레이어는 ArgoCD GitOps에 의존한다.
- 기존 `argocd/` 디렉터리와 Application 정의가 제거되어 현재는 **ArgoCD 설치만 있고 어떤 브랜치도 바라보지 않는 상태**다.
- Kubernetes 커뮤니티에서는 [ArgoCD App of Apps 패턴](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#applications)과 [Kustomize/Helm 혼합 전략(CNCF GitOps WG, GitOps Days 발제 등)]이 가장 유지보수성이 높은 접근으로 권장된다.

## 외부 레퍼런스에서 얻은 핵심 인사이트
1. **App of Apps**  
   - Root Application이 하위 Application(또는 ApplicationSet)을 선언하고 `sync-wave`로 **의존성/순서 제어**를 맡는다.
   - Root App은 “구조”, 하위 App은 “콘텐츠”에 집중한다. (Argo 공식 문서 및 Intuit 사례)
2. **패키징 혼합 전략**  
   - **Kustomize**: 네임스페이스, 네트워크 정책, API 마이크로서비스처럼 “우리 코드” 기반 YAML에 적합.
   - **Helm**: PostgreSQL, RabbitMQ, kube-prometheus-stack 같이 **업스트림 Chart 재사용**이 효율적인 구성요소에 적합.
   - ArgoCD는 한 리포지토리 안에서도 Helm/Kustomize를 동시에 관리할 수 있다.

## 현재 클러스터와의 매핑
| Wave | 계층 | 예시 리소스 | 패키징 | 저장 경로 |
| --- | --- | --- | --- | --- |
| -1 | Security Foundation | OPA/Kyverno, External Secrets, (옵션) cert-manager | Helm+Kustomize 혼합 | `k8s/security`, `charts/security/*` (planned) |
| 0~1 | Infrastructure | Namespaces, NetworkPolicies, RBAC | Kustomize | `k8s/infrastructure` |
| 20 | AWS Load Balancer Controller | Helm | `eks/aws-load-balancer-controller` |
| 30 | Platform Services (Reserved) | Node Lifecycle, External Secrets | Kustomize/Helm 혼합 | `k8s/platform/*` |
| 40 | Observability | kube-prometheus-stack, Grafana | Helm | `charts/observability/kube-prometheus-stack` |
| 60 | Data Layer | PostgreSQL, Redis, RabbitMQ | Helm | `charts/data/<component>` |
| 70 | GitOps Tools | Atlantis | Helm | `charts/platform/atlantis` |
| 80 | API Services | auth, my, scan, character, ... | Kustomize overlays | `k8s/overlays/<domain>` |

## 제안하는 App of Apps 구조
```
backend/
├── argocd/
│   ├── root-app.yaml
│   └── apps/                      # develop 브랜치 기준 App of Apps
│       ├── 00-foundations.yaml
│       ├── 10-infrastructure.yaml
│       ├── 20-alb-controller.yaml
│       ├── 30-platform.yaml
│       ├── 40-monitoring.yaml     # Helm → charts/observability/…
│       ├── 50-data-operators.yaml
│       ├── 60-data-clusters.yaml
│       ├── 70-gitops-tools.yaml
│       └── 80-apis-app-of-apps.yaml
├── k8s/
│   ├── infrastructure/
│   ├── namespaces/
│   ├── networkpolicies/
│   └── overlays/<domain>/ (재작성 예정)
└── charts/
    ├── observability/kube-prometheus-stack/
    ├── data/databases/
    └── platform/ … (Helm 모듈 확장 영역)
```

### Root Application 설정
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-app
  namespace: argocd
spec:
  project: root
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: develop             # stage/main 브랜치로 승격 가능
    path: argocd/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - Validate=true
      - CreateNamespace=true
```

### 예시 – Infrastructure App (Kustomize)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: infrastructure
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  project: foundation
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: develop
    path: k8s/infrastructure
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - Validate=true
      - CreateNamespace=true
```

### 예시 – Observability App (Helm)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: monitoring
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "40"
spec:
  project: default
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: develop
    path: charts/observability/kube-prometheus-stack
    helm:
      releaseName: monitoring
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: monitoring
```

> **환경 분리**: Google/Airbnb 사례처럼 `argocd/applications/prod/*.yaml`, `.../stage/*.yaml` 로 디렉터리를 나누고 Root App이 `values.environment`에 따라 서로 다른 브랜치·경로를 바라보게 하면 멀티 클러스터/릴리스 트레인 운영에 유리하다.

### 예시 – API ApplicationSet (Kustomize overlays)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: api-services
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "80"
spec:
  generators:
    - git:
        repoURL: https://github.com/SeSACTHON/backend
        revision: develop
        directories:
          - path: k8s/overlays/*
  template:
    metadata:
      name: "api-{{path.basename}}"
    spec:
      project: apps
      source:
        repoURL: https://github.com/SeSACTHON/backend
        targetRevision: develop
        path: "{{path}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{path.basename}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ApplyOutOfSyncOnly=true
        retry:
          limit: 3
          backoff:
            duration: 15s
            factor: 2
            maxDuration: 5m
```

## 실행 계획
1. **문서/폴더 리팩토링**  
   - `docs/pr_descriptions/`에 흩어져 있던 Markdown을 모았다.  
   - App of Apps 관련 기존 문서는 제거하고 본 파일을 기준으로 새 구조를 정의한다.
2. **Repo 구조 복원**  
   - `argocd/apps/*.yaml` 에 Wave 순서를 정의하고 `targetRevision: develop` 을 공통 적용.
   - `charts/observability/*` 처럼 Helm 모듈을 `charts/` 아래에 배치하고, `k8s/` 는 Kustomize 전용으로 유지.
3. **ArgoCD에 등록**  
   - `kubectl apply -f argocd/root-app.yaml`
   - `argocd app diff root-app` / `argocd app sync root-app` 로 검증.
4. **패키징 가이드**  
   - 신규 리소스 추가 시 “Helm chart인지, Kustomize overlay인지” 명시하고 동일 패턴을 유지한다.

이 구조를 적용하면 Terraform/Ansible로 구축한 인프라 위에 ArgoCD(App of Apps)가 계층별로 리소스를 자동 배포하며, Kustomize와 Helm을 상황에 맞게 혼용할 수 있다.

## 🎯 운영 권장사항
- Root App + Wave 구조를 유지하며, 각 wave에 맞는 Kustomize/Helm 방식을 명시한다.
- Helm 패키지는 `charts/README.md` 의 가이드를 따라 dependency/values 를 관리하고, Kustomize 트리는 `k8s/` 아래에서만 유지한다.
- 환경별 브랜치·경로(`argocd/applications/{stage,prod}`)를 분리해 멀티 릴리스 트레인을 운영한다.
- ApplicationSet에서는 git/directory generator를 사용해 신규 도메인 추가 시 수작업을 줄이고, `syncOptions`/`retry`를 표준화한다.
- Wave -1~1은 SRE/Security 프로젝트, Wave 2 이후는 도메인 프로젝트로 나눠 ArgoCD Project RBAC를 강화한다.
- Root App과 각 Wave에는 ArgoCD Notifications를 붙여 Slack/PagerDuty로 배포 상태를 전파한다.
- 이 문서(`docs/architecture/gitops/APP-OF-APPS-DECISION.md`)와 Wave별 운영 책임 문서를 업데이트해 신규 팀 온보딩을 돕는다.
