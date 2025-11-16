# RBAC 정책 (Namespace & Feature 기반)

> **목적**: 현재 네임스페이스 구조(비즈니스 API, 데이터 계층, 모니터링, 인프라)에 맞춰 Kubernetes RBAC을 표준화해 권한 범위를 최소 권한 원칙(Least Privilege)으로 유지한다.  
> **레퍼런스**: 
> - Kubernetes 공식 문서 *"Using RBAC Authorization"*  
> - CNCF App Delivery WG 보안 권고(*Least Privilege for GitOps*)  
> - NSA/CISA Kubernetes Hardening Guide (2023)

---

## 0. 환경별 RBAC 전략

| 환경 | 정책 | RoleBinding 위치 | 이유 |
|------|------|------------------|------|
| **dev** | 모든 인증된 사용자 → `cluster-admin` | `workloads/rbac-storage/overlays/dev/cluster-role-bindings.yaml` | 빠른 개발/디버깅, 네임스페이스 제약 없음 |
| **prod** | ServiceAccount별 최소 권한 (Least Privilege) | `workloads/rbac-storage/overlays/prod/role-bindings.yaml` | 보안, 감사 추적, 장애 격리 |

### Dev 환경 (Full Access)

```yaml
# workloads/rbac-storage/overlays/dev/cluster-role-bindings.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dev-full-access
roleRef:
  kind: ClusterRole
  name: cluster-admin
subjects:
  - kind: Group
    name: system:authenticated  # 모든 인증된 사용자
```

### Prod 환경 (최소 권한)

- `platform-admin` → ArgoCD Application Controller SA
- `data-ops` → Postgres/Redis/RabbitMQ Operator SA (각 네임스페이스별 Role)
- `observability-reader` → Prometheus SA (ClusterRole, ReadOnly)

상세 바인딩: `workloads/rbac-storage/overlays/prod/role-bindings.yaml`

### Terraform IRSA 연계

모든 ServiceAccount의 AWS IAM 권한은 Terraform에서 생성:

| ServiceAccount | Namespace | IAM Role (Terraform) | SSM Parameter 경로 |
|---------------|-----------|----------------------|-------------------|
| `external-secrets-sa` | `platform-system` | `aws_iam_role.external_secrets` | `/sesacthon/{env}/iam/external-secrets-role-arn` |
| `postgres-operator` | `data-system` | `aws_iam_role.postgres_operator` | `/sesacthon/{env}/iam/postgres-operator-role-arn` |
| `aws-load-balancer-controller` | `kube-system` | `aws_iam_role.alb_controller` | `/sesacthon/{env}/iam/alb-controller-role-arn` |

파일: `terraform/irsa-roles.tf`

---

## 1. 네임스페이스 분류 요약

| Tier | Namespace | 주요 리소스 | 특징 |
|------|-----------|-------------|------|
| **Business Logic** | `auth`, `my`, `scan`, `character`, `location`, `info`, `chat` | API Deployment/Service/ConfigMap/Secret | 애플리케이션 팀별 관리, 데이터 접근은 Service 호출로 제한 |
| **Integration** | `messaging` | RabbitMQ Operator + Cluster CR | 서버 간 메시징, 고가용성 필요 |
| **Data (Postgres)** | `postgres` | PostgreSQL Operator/Instances | DB 계층, tier=data |
| **Data (Redis)** | `redis` | Redis Operator/Instances | Cache 계층, tier=data |
| **Observability** | `monitoring` | kube-prometheus-stack, Grafana | 플랫폼 팀 관리, 모든 네임스페이스 리드 |
| **Infrastructure** | `atlantis`, `workers`(필요 시) | Terraform/AWS credential Secret, Worker Daemon | DevOps 도구 전용 |

이 문서는 위 분류를 기준으로 RBAC 역할을 정의한다.

---

## 2. 역할 모델

| 역할 | ClusterRole 범위 | Namespace 접근 | 사용 주체 | 허용 작업 |
|------|------------------|----------------|-----------|-----------|
| **platform-admin** | Cluster-scoped (nodes, CRDs, namespaces, RBAC) | 전체 | Platform/SRE | 인프라 운영 전권 (Change window 필요) |
| **data-ops** | Namespaced + data/messaging | `postgres`, `redis`, `messaging` | DB 팀 | StatefulSet/Secret 관리, Snapshot/Backup Job 실행 |
| **api-dev** | Namespaced | 각 도메인(`auth` 등) | 서비스 팀 | Deployment/Service/ConfigMap/Secret(own) 수정, 다른 namespace 읽기 금지 |
| **observability** | ClusterRole(ReadOnly) | 모든 namespace Read | Monitoring 팀, Grafana SA | Pods/Services/Endpoints/CustomMetrics 읽기 |
| **automation-ci** | ClusterRole(Argo/Atlantis) | 대상 namespace | ArgoCD, Atlantis SA | GitOps sync (`apps`, `deployments` 패치) |
| **read-only** | View cluster role | 제한 없음 (audit) | 보안/Audit | 리소스 조회만 허용 |

### 네임스페이스-역할 매핑
- Business Logic: `api-dev` + `automation-ci`
- Data/Messaging: `data-ops` + `automation-ci`
- Monitoring: `observability` + `platform-admin`
- Infrastructure: `platform-admin` + `automation-ci`

---

## 3. ClusterRole & RoleBinding 예시

### 3.1 api-dev (도메인 팀)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: api-dev
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["services", "configmaps", "secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["autoscaling"]
    resources: ["horizontalpodautoscalers"]
    verbs: ["get", "list", "watch", "update"]
```

```yaml
# auth 팀 예시
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: auth-api-dev-binding
  namespace: auth
subjects:
  - kind: User
    name: team-auth
roleRef:
  kind: ClusterRole
  name: api-dev
  apiGroup: rbac.authorization.k8s.io
```

### 3.2 data-ops

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: data-ops
rules:
  - apiGroups: ["*"]
    resources: ["postgresclusters", "redisclusters", "statefulsets", "persistentvolumeclaims"]
    verbs: ["*"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
```

RoleBinding을 `postgres`, `redis`, `messaging` 네임스페이스에 각각 생성한다.

### 3.3 observability (읽기 전용)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: observability-view
rules:
  - apiGroups: ["", "apps", "networking.k8s.io", "monitoring.coreos.com"]
    resources: ["pods", "services", "ingresses", "prometheusrules", "servicemonitors"]
    verbs: ["get", "list", "watch"]
```

Grafana/Prometheus ServiceAccount를 위해 `ClusterRoleBinding`으로 묶는다.

---

## 4. 운영 지침

1. **Tier 기반 접근 정책**  
   - 네임스페이스 레이블 `tier`를 기준으로 선택적 RoleBinding 자동화를 작성한다.  
   - 예: `kubectl get ns -l tier=business-logic -o name | xargs -I{} kubectl apply -f rolebinding-template.yaml`.

2. **GitOps 연계**  
   - RBAC YAML도 Git으로 관리하고 ArgoCD `platform` 프로젝트로 Sync한다.  
   - 변경 시 Change Request + Peer Review 필수.

3. **비밀 관리**  
   - Operators/Controller만 Secret 생성 권한을 갖도록 하고, 사람은 ExternalSecrets/ESO를 통해 간접 수정.  
   - Break-glass가 필요한 경우 전용 `cluster-admin` RoleBinding을 시간 제한으로 발급.

4. **감사**  
   - `kubectl auth can-i --as=<user> --list`로 분기마다 권한 검증.  
   - CloudTrail/OPA Gatekeeper 정책으로 ClusterRoleBinding 생성 이벤트를 감시.

---

## 5. 향후 과제

1. **Namespace Self-Service**: Service Catalog 도입 시 api-dev 역할 자동 발급.  
2. **OPA/Gatekeeper**: Tier/Namespace 조합이 아닌 RoleBinding 생성 시 거부 정책 추가.  
3. **Secret Zero Trust**: External Secrets Operator + IAM Roles for ServiceAccount(IRSA) 연계로 AWS 권한 최소화.

---

> 본 RBAC 정책은 현재 네임스페이스 및 기능 구성을 기준으로 작성되었다. 네임스페이스 추가/변경 시 Role 정의와 Binding을 동일 PR에서 갱신해야 하며, GitOps 파이프라인을 통해 자동으로 반영된다.

