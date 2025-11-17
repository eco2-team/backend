# RBAC & Storage (Wave 0)

Kubernetes RBAC 역할 및 StorageClass 정의.

## 구조

- `base/`:
  - `service-accounts.yaml`: IRSA 대상 ServiceAccount (ExternalSecrets, Postgres Operator, ALB Controller, ExternalDNS)
  - `cluster-roles.yaml`: platform-admin, observability-reader, read-only
  - `namespaced-roles.yaml`: data-ops (postgres/redis/rabbitmq), api-dev (auth)
  - `storage-class.yaml`: gp3 기본 StorageClass

- `overlays/dev/`: base 참조 (동일)
- `overlays/prod/`: base 참조 (동일)

## IRSA (IAM Roles for Service Accounts)

ServiceAccount 주입 파이프라인:

1. Terraform (`terraform/irsa-roles.tf`)이 IRSA Role + SSM Parameter(`/sesacthon/{env}/iam/*-role-arn`) 생성
2. `workloads/secrets/external-secrets/{env}/sa-irsa-patch.yaml`이 `*-sa-irsa-values` Secret을 생성
3. `irsa-annotator` Job(`workloads/secrets/external-secrets/base/irsa-annotator-*.yaml`)이 Secret 내용을 읽어 ServiceAccount에 `eks.amazonaws.com/role-arn`을 주입

## 배포

Wave 0에서 Namespace 직후 적용됨.

```bash
kubectl apply -k workloads/rbac-storage/overlays/dev
```

## 참고

- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`
- `terraform/irsa-roles.tf`

