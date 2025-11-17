# RBAC & Storage (Wave 0)

Kubernetes RBAC 역할 및 StorageClass 정의.

## 구조

- `base/`:
  - `service-accounts.yaml`: AWS 리소스를 사용하는 ServiceAccount (ExternalSecrets, Postgres Operator, ALB Controller, ExternalDNS)
  - `cluster-roles.yaml`: platform-admin, observability-reader, read-only
  - `namespaced-roles.yaml`: data-ops (postgres/redis/rabbitmq), api-dev (auth)
  - `storage-class.yaml`: gp3 기본 StorageClass

- `overlays/dev/`: base 참조 (동일)
- `overlays/prod/`: base 참조 (동일)

## AWS 권한 주입 전략

- **현재(임시)**: OIDC/IRSA가 준비될 때까지 Access Key/Secret Key를 `aws-global-credentials` Secret으로 만들어 Pod에 환경변수로 주입한다.  
  - 네임스페이스: `kube-system`, `platform-system`  
  - Secret 키: `aws_access_key_id`, `aws_secret_access_key`  
  - 관련 Helm values(`platform/helm/*/values/{env}.yaml`)에서 env → `valueFrom.secretKeyRef`로 사용
- **향후(IRSA 재도입)**:
  1. Terraform (`terraform/irsa-roles.tf`)에서 `enable_irsa = true`로 바꾸고 OIDC Issuer를 등록  
  2. `*-sa-irsa-values` ExternalSecret 및 `irsa-annotator` Hook을 다시 활성화  
  3. ServiceAccount annotation `eks.amazonaws.com/role-arn`을 통해 최소 권한 IRSA로 전환

## 배포

Wave 0에서 Namespace 직후 적용됨.

```bash
kubectl apply -k workloads/rbac-storage/overlays/dev
```

## 참고

- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`
- `terraform/irsa-roles.tf`

