# Sync Wave 별 ConfigMap / Secret 선행 전략

> **목표**: 고정된 Sync Wave 순서에 맞춰 각 리소스가 참조하는 ConfigMap/Secret을 사전에 배포하고, Terraform/CI에서 값을 안전하게 주입하는 절차를 정의한다.  
> **참고 문서**: `ARGOCD_SYNC_WAVE_PLAN.md`, `TERRAFORM_SECRET_INJECTION.md`, `RBAC_NAMESPACE_POLICY.md`

---

## 1. Terraform Output 정리

현재 `terraform/outputs.tf`에서 제공되는 값 중 ConfigMap/Secret으로 노출할 대상:

| 출력 키 | 용도 | 비고 |
|---------|------|------|
| `vpc_id` | ALB Controller, IngressClassParams | Wave 10/16 선행 데이터 |
| `cluster_info.api_ips` 등 | 모니터링/운영 참고 | 민감도 낮음(정보용) |
| `acm_certificate_arn` | Ingress(ALB) TLS 연결 | ACM은 클러스터 외부 배포지만 ARN을 Helm values에 주입해야 함 |
| `dns_records.*` | Ingress/External DNS | 옵션 (domain 설정 시) |
| `aws_region` | Helm values 공통 파라미터 | Wave 0 ConfigMap으로 배포 |

> **부족한 값**: ALB/Subnet ID, Security Group ID, Private/Public Subnet 목록 등은 현재 output에 없음. 향후 `module.vpc.public_subnet_ids`, `private_subnet_ids`, `alb_security_group_id` 등을 출력해 `/sesacthon/{env}/network/*` Parameter에 저장해야 한다.

Terraform → SSM/Secrets Manager 저장 경로 예시:
- `/sesacthon/{env}/network/vpc-id`
- `/sesacthon/{env}/network/public-subnets`
- `/sesacthon/{env}/network/sg-alb`
- `/sesacthon/{env}/ingress/acm-arn`

---

## 2. Sync Wave vs ConfigMap/Secret 선행 조건

| Wave | 리소스 묶음 | 필요한 CM/Secret | 값 출처 | 비고 |
|------|-------------|------------------|---------|------|
| **-1** | CRD 번들 | (없음) | - | CRD는 매니페스트만 배포 |
| **0** | RBAC / SA / Storage | `cluster-config` ConfigMap (`aws_region`, `env`, `domain`), IRSA role annotations | Terraform vars, GitHub env | 모든 Helm chart에서 공통 참조 |
| **5** | Network (CNI, default NP) | CNI tuning ConfigMap(선택) | 수동 설정 | Calico Felix 설정 등 |
| **10** | ALB Controller (Helm) | `alb-controller-values` Secret/CM: `clusterName`, `vpcId`, `region`, `awsAccountId` | Terraform outputs (`vpc_id`, `aws_region`) | Secret은 SSM → ExternalSecret으로 주입 |
| **16** | DNS Automation | `external-dns-sa-irsa-values` Secret (IRSA), Ingress hostname annotations | SSM `/iam/external-dns-role-arn`, Git 매니페스트 | Route53 Alias 자동 생성 전 Secret 필요 |
| **20** | Monitoring Operator (Helm) | `alertmanager-config` Secret, `grafana-datasource` ConfigMap, `grafana-admin` Secret(`/platform/grafana-admin-password`) | Slack/Webhook Secrets(GitHub `secrets.SLACK_WEBHOOK` 등), Internal URL, SSM Parameter Store | Helm valueFiles에서 참조 |
| **25** | Data Operators (Helm) | S3 Backup credential Secret, Operator default ConfigMap | Terraform (S3 bucket), AWS IAM | ExternalSecrets 권장 |
| **30** | Monitoring CR (Prometheus/Alertmanager) | Alert rule ConfigMap, Grafana dashboard ConfigMap, SLO Secret(옵션) | Git repo / Config repo | Wave 25보다 앞선 commit에 포함 |
| **35** | Data CR (PostgresCluster, RedisCluster, RabbitmqCluster) | DB 사용자 Secret, TLS Secret, ConfigMap(연결 모드) | External Secrets Operator (SM/Parameter Store) | `postgresql-secret`(`/sesacthon/{env}/data/postgres-password`), `redis-secret`(`/data/redis-password`), `rabbitmq-default-user`(`/data/rabbitmq-password`) |
| **40** | Exporters | Target credential Secret (DB/Redis metrics user) | Data CR과 동일 Secret reuse | Secrets 존재를 체크 후 배포 |
| **50** | Tools (Atlantis, Workflows) | `atlantis-git-token` Secret, Slack Webhook Secret | GitHub `secrets.GH_TOKEN`, `secrets.SLACK_WEBHOOK` | GitHub Actions에서 Kubernetes Secret 생성 or ExternalSecret |
| **60** | 서비스/워크로드 (API, Worker) | 애플리케이션 ConfigMap/Secret (API URL, env vars, GHCR pull secret) | GitHub Secrets (`GH_TOKEN` → `dockerconfigjson`) | `GH_TOKEN`은 GitHub Actions에서 `kubectl create secret docker-registry`로 Wave 55 이전 생성 |
| **65** | Ingress (ALB) | TLS Secret (ACM ARN reference), host routing ConfigMap(옵션) | ACM(외부), Terraform output | Ingress 배포 직전 Secret 존재 확인 |

> **Wave 11 (Secrets CR)**: `workloads/secrets/external-secrets/{env}`를 통해 `alb-controller-values`, `alb-sa-irsa-values`, `external-dns-sa-irsa-values`, `postgresql-secret`, `redis-secret`, `rabbitmq-default-user`, `grafana-admin`, `argocd-admin-secret` 등이 `/sesacthon/{env}/**` SSM 경로에서 동기화된다.

### GitHub Secrets
- `secrets.GH_TOKEN`: GHCR 이미지 Pull Secret 생성에 사용 (Wave 60 이전).  
  ```bash
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=gh-actions \
    --docker-password=$GH_TOKEN \
    -n <namespace>
  ```
- `secrets.SLACK_WEBHOOK`, `secrets.ATLANTIS_GH_TOKEN` 등은 ExternalSecrets 또는 ArgoCD Helm values로 전달.

---

## 3. 배포 절차 예시

1. **Terraform Apply**  
   - `vpc_id`, `aws_region`, `acm_certificate_arn` 등 출력 후 `aws_ssm_parameter` 리소스로 저장 (`TERRAFORM_SECRET_INJECTION.md` 참고).
2. **External Secrets Operator (Wave 20 이전)**  
   - `ClusterSecretStore`에서 `/sesacthon/{env}/**` 경로를 읽어 Kubernetes Secret 생성.
3. **ConfigMap/Secret 선행 배포**  
   - Wave 0/5에서 `cluster-config`, `alb-controller-values` 등을 ArgoCD Application으로 등록.  
   - Helm chart들은 `valuesFrom` 또는 `envFrom`으로 해당 Secret을 참조.
4. **리소스 Wave 배포**  
   - Operators(Helm) → Instances(CR) → Exporters → Tools → Workloads → Ingress 순서를 고정.  
   - 각 Wave 배포 전에 `kubectl get secret/configmap`으로 존재 여부 검증 (`argocd app wait` hook 또는 PreSync Script 활용).

---

## 4. 운영 체크리스트

- [ ] Terraform output에 Subnet/SG ID 추가 (`output "public_subnet_ids"`, `"alb_security_group_id"` 등).  
- [ ] `/sesacthon/{env}/` Parameter 경로 표준화와 IAM 권한(`ssm:GetParameter`) 설정.  
- [ ] GHCR Pull Secret은 모든 Business Logic namespace에 존재하는지 주기적으로 `kubectl get secret ghcr-secret -n <ns>` 검사.  
- [ ] ConfigMap/Secret 변경 시 ArgoCD가 먼저 Sync되도록 Wave 어노테이션(`sync-wave: <resource wave - 1>`)을 부여.  
- [ ] Secret Rotation 시 ExternalSecrets refresh 주기를 1h 이하로 설정하고, Rotation 완료 후 Wave 리소스 재배포 필요 여부 확인.

---

> 이 매트릭스는 Sync Wave를 규정된 순서로 유지하기 위한 기준 문서이다. 새로운 Helm 차트나 CR을 추가할 때는 먼저 필요한 ConfigMap/Secret을 선행 Wave에 배포해야 하며, Terraform/CI에서 공급 가능한 값인지 검토 후 `TERRAFORM_SECRET_INJECTION` 전략을 업데이트한다.

