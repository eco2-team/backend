# RBAC & Storage (Wave 03)

`workloads/rbac-storage/`는 Wave 02 Namespace 직후 적용되는 ServiceAccount·Role·StorageClass를 정의합니다. External Secrets, AWS Load Balancer Controller, ExternalDNS, Postgres/Redis Operator 등이 요구하는 계정과 권한을 한곳에서 선언합니다.

## 디렉터리 구조
- `base/`
  - `service-accounts.yaml`: External Secrets Operator, Postgres Operator, Redis Operator, AWS Load Balancer Controller, ExternalDNS용 ServiceAccount
  - `cluster-roles.yaml`: `platform-admin`, `observability-reader`, read-only ClusterRole
  - `cluster-rolebindings.yaml`: Argo CD / Observability 계정 바인딩 기본값
  - `namespaced-roles.yaml`: `data-ops`(postgres/redis/rabbitmq), `api-dev` 등 네임스페이스 한정 Role
  - `namespaced-rolebindings.yaml`: Operator/서비스 계정을 각 Role에 묶는 binding
  - `storage-class.yaml`: `gp3` + `ebs.csi.aws.com` Provisioner, IOPS/Throughput 기본값
- `dev/`: base를 참조하고 `cluster-role-bindings.yaml`에서 개발 편의상 `system:authenticated` → `cluster-admin` 바인딩을 추가
- `prod/`: 운영 환경 binding (Argo CD Controller, Prometheus ServiceAccount, data-ops RoleBinding 등)을 별도 정의

## AWS 권한 주입 전략
- **현재(임시)**: IRSA를 재정비하는 동안 Access Key를 `aws-global-credentials` Secret으로 주입하고, Helm Chart(`clusters/{env}/apps/15-alb-controller.yaml`, `16-external-dns.yaml`, `10-secrets-operator.yaml`)에서 `valueFrom.secretKeyRef`로 참조합니다.
- **향후(IRSA)**:
  1. Terraform `terraform/irsa-roles.tf` 의 `enable_irsa` 플래그를 다시 활성화하고 OIDC Issuer를 등록
  2. IRSA 전용 ExternalSecret (`*-sa-irsa-values`)과 `irsa-annotator` Hook을 복구
  3. ServiceAccount annotation `eks.amazonaws.com/role-arn`을 설정해 최소 권한 Role을 부여

## 배포

Wave 03에서 Namespace 직후 적용됩니다.

```bash
# dev
kubectl apply -k workloads/rbac-storage/dev

# prod
kubectl apply -k workloads/rbac-storage/prod
```

## 참고

- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`
- `docs/troubleshooting/2025-11-19-rabbitmq-redis.md` (RabbitMQ data-ops Role 유지 배경)
- `terraform/irsa-roles.tf`
