# RBAC & Storage (Wave 0)

Kubernetes RBAC 역할 및 StorageClass 정의.

## 구조

- `base/`:
  - `service-accounts.yaml`: IRSA 어노테이션이 포함된 SA (ExternalSecrets, Postgres Operator, ALB Controller)
  - `cluster-roles.yaml`: platform-admin, observability-reader, read-only
  - `namespaced-roles.yaml`: data-ops (postgres/redis/rabbitmq), api-dev (auth)
  - `storage-class.yaml`: gp3 기본 StorageClass

- `overlays/dev/`: base 참조 (동일)
- `overlays/prod/`: base 참조 (동일)

## IRSA (IAM Roles for Service Accounts)

ServiceAccount의 `eks.amazonaws.com/role-arn` 어노테이션은 ExternalSecret으로 주입된다:
- `/sesacthon/{env}/iam/external-secrets-role-arn`
- `/sesacthon/{env}/iam/postgres-operator-role-arn`
- `/sesacthon/{env}/iam/alb-controller-role-arn`

실제 IAM Role은 `terraform/irsa-roles.tf`에서 생성한다.

## 배포

Wave 0에서 Namespace 직후 적용됨.

```bash
kubectl apply -k workloads/rbac-storage/overlays/dev
```

## 참고

- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`
- `terraform/irsa-roles.tf`

