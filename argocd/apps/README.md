# ArgoCD Apps Directory Structure

이 디렉토리는 실제 Kubernetes 리소스의 소스입니다.

## 디렉토리 구조

```
apps/
├── apis/                        # Tier 2: Business Logic
│   ├── auth/                    → k8s/overlays/auth
│   ├── my/                      → k8s/overlays/my
│   ├── scan/                    → k8s/overlays/scan
│   ├── character/               → k8s/overlays/character
│   ├── location/                → k8s/overlays/location
│   ├── info/                    → k8s/overlays/info
│   ├── chat/                    → k8s/overlays/chat
│   └── workers/                 # Tier 3: Async Workers
│       ├── celery-worker/       (Placeholder)
│       └── flower/              (Placeholder)
│
├── mq/                          # Tier 3: Message Queue
│   └── kustomization.yaml       (Placeholder - Ansible 배포)
│
└── data/                        # Tier 4: Persistence
    ├── postgres/                (Placeholder - Ansible 배포)
    └── redis/                   (Placeholder - Ansible 배포)
```

## Tier 구조

- **Tier 1**: Infrastructure (ALB, Ingress)
- **Tier 2**: Business Logic (API Services)
- **Tier 3**: Message Queue (RabbitMQ, Celery Workers)
- **Tier 4**: Persistence (PostgreSQL, Redis)

## 참조 관계

### APIs → k8s/overlays/
ApplicationSet `70-appset.yaml`이 자동으로 `k8s/overlays/{domain}`을 참조합니다.
실제 Kustomize 소스는 `k8s/overlays/` 디렉토리에 있습니다.

### Data → Ansible
현재 PostgreSQL, Redis, RabbitMQ는 **Ansible이 배포**합니다.
향후 Operator CR로 전환 시 이 디렉토리에 정의합니다.

### Workers → Placeholder
현재는 비어있습니다. Celery Worker 배포 시 여기에 추가합니다.

## Wave 순서

```
Wave -1: Foundations (Namespaces, CRDs)
Wave 0:  Infrastructure (Ingress)
Wave 10: Platform (cert-manager 등)
Wave 20: Monitoring (Prometheus, Grafana)
Wave 25: Data Operators (Placeholder)
Wave 30: Data Clusters (PostgreSQL, Redis, RabbitMQ)
Wave 50: GitOps Tools (Atlantis)
Wave 60: API Services (7개 API)
Wave 65: Workers (Celery, Flower)
```

## 기존 구조와의 차이

### 이전:
```
argocd/
├── root-app.yaml
└── apps/
    ├── infrastructure.yaml       (Application 정의)
    └── api-services.yaml         (ApplicationSet 정의)
```

### 현재:
```
argocd/
├── root-app.yaml                 (components/ 참조)
├── components/                   (Application/ApplicationSet 정의)
│   ├── 00-foundations.yaml
│   ├── ...
│   └── 70-appset.yaml
└── apps/                         (실제 Kubernetes 리소스)
    ├── apis/
    ├── mq/
    └── data/
```

**핵심 차이점**:
- `components/`: Application/ApplicationSet **정의만**
- `apps/`: 실제 Kubernetes **리소스만**
- 명확한 계층 분리!

