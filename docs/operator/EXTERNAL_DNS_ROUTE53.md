# ExternalDNS & Route53 동기화 가이드

> **목적**: AWS Load Balancer Controller가 생성하는 Ingress/ALB 정보를 자동으로 Route53에 반영하기 위해 ExternalDNS를 Helm + IRSA 패턴으로 배포한다.  
> **적용 대상**: `images.growbin.app`를 제외한 애플리케이션/플랫폼 도메인 (api, argocd, grafana 등)  
> **작성일**: 2025-11-16 · **Wave**: 16

---

## 1. 아키텍처 요약

```text
Ingress/Service (Wave ≥10)
        │ annotations
        ▼
AWS Load Balancer Controller (Wave 15) ──▶ ALB DNS
        │
        ▼
ExternalDNS (Wave 16, Helm)
        │ assumes IAM Role (IRSA)
        ▼
Route53 (api.growbin.app, argocd.growbin.app, …)
```

1. **Helm Chart**: `kubernetes-sigs/external-dns`, version `1.15.2` (이미지 `registry.k8s.io/external-dns/external-dns:v0.14.2`).  
2. **ServiceAccount**: `platform-system/external-dns` (RBAC Wave 3) + IRSA (`/sesacthon/{env}/iam/external-dns-role-arn`).  
3. **IAM Policy**: `route53:List*`, `route53:ChangeResourceRecordSets` (resource `*`, Route53 제약상 wildcard 필요).  
4. **Sync Wave**: Namespaces → RBAC → NetworkPolicy → Secrets → ALB Controller → **ExternalDNS** → Monitoring.  
5. **Ingress 주석**: `external-dns.alpha.kubernetes.io/hostname`, `target` 등 Git으로 관리.  

---

## 2. 배포 절차

| 단계 | 파일/경로 | 설명 |
|------|-----------|------|
| 1 | `terraform/irsa-roles.tf`, `ssm-parameters.tf` | IRSA Role (`external-dns`) + SSM `/sesacthon/{env}/iam/external-dns-role-arn` 추가 |
| 2 | `workloads/rbac-storage/base/service-accounts.yaml` | `external-dns` ServiceAccount 정의 (Wave 3) |
| 3 | `workloads/rbac-storage/{env}/patch-sa-irsa.yaml` | 각 환경에 IAM Role ARN 주입 |
| 4 | `workloads/secrets/external-secrets/{env}/sa-irsa-patch.yaml` | IRSA ARN을 Secret으로 동기화 (Wave 11) |
| 5 | `platform/helm/external-dns/` | Helm ApplicationSet + values(dev/prod) 생성 |
| 6 | `clusters/{env}/apps/16-external-dns.yaml` | Sync Wave 16 Application 등록 |
| 7 | `docs/architecture/...` | Sync Wave/네임스페이스 문서 업데이트 |

---

## 3. Helm 값 요약

```yaml
serviceAccount:
  create: false
  name: external-dns

provider: aws
policy: upsert-only
registry: txt
txtOwnerId: sesacthon-dev   # prod는 sesacthon-prod
domainFilters:
  - growbin.app
sources:
  - ingress
  - service
extraArgs:
  - aws-zone-type=public
  - aws-prefer-cname
env:
  - name: AWS_REGION
    value: ap-northeast-2
```

> Route53 Hosted Zone ID는 ExternalDNS가 `ListHostedZones` 후 자동 탐색한다. `domainFilters`를 지정하여 `growbin.app` 외 레코드는 생성하지 않는다.

---

## 4. Sync Wave & 의존성

| Wave | 리소스 | 비고 |
|------|--------|------|
| 0 | Namespaces (`workloads/namespaces`) | `platform-system` |
| 3 | RBAC/ServiceAccounts | `external-dns` SA 및 annotation |
| 5 | NetworkPolicy | `platform-system` egress 허용 (`kube-system`, AWS API) |
| 10 | ExternalSecrets Operator | IRSA Secret 생성 준비 |
| 11 | ExternalSecret (IRSA) | `/sesacthon/{env}/iam/external-dns-role-arn` → Secret |
| 15 | ALB Controller | Ingress → ALB 생성 |
| **16** | **ExternalDNS (Helm)** | Route53 Alias 관리 |
| 20+ | Monitoring/Data/Apps | Route53 레코드가 이미 존재해야 함 |

---

## 5. 검증 절차

1. **Pod 상태**  
   ```bash
   kubectl -n platform-system get deploy external-dns
   kubectl -n platform-system logs deploy/external-dns | tail
   ```
2. **Route53 레코드**  
   ```bash
   aws route53 list-resource-record-sets --hosted-zone-id ZXXXXXXXX --query "ResourceRecordSets[?Name == 'api.growbin.app.']"
   ```
3. **외부 확인**  
   ```bash
   dig +short api.growbin.app
   curl -I https://api.growbin.app/health
   ```
4. **Ingress 주석**: 모든 Ingress는 `external-dns.alpha.kubernetes.io/hostname`를 명시해야 한다. Git PR 템플릿에 체크 항목을 추가한다.

---

## 6. 운영 메모

- ExternalDNS는 Route53 레코드를 “선언적”으로 유지한다. Git에서 Ingress를 삭제하면 레코드도 자동 제거되므로, 임시 도메인은 `{ env }` 전용 branch에서만 운영한다.
- `txtOwnerId`는 환경별로 고유해야 하며, 동일 Hosted Zone을 공유하는 여러 클러스터를 구분하기 위한 값이다.
- CloudFront(`images.growbin.app`)처럼 Terraform이 별도 Alias를 관리하는 레코드에는 ExternalDNS를 사용하지 않는다 (domainFilter 예외 처리 필요 시 `excludeDomains` 사용).


