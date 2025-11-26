# `workloads/` 개요

`workloads/` 디렉터리는 **Helm으로 관리하지 않는 모든 Kubernetes 리소스**(Namespace, RBAC, NetworkPolicy, ExternalSecret, API Deployment 등)를 Kustomize로 정의합니다.
Argo CD App-of-Apps가 참조하는 경로는 `clusters/{env}/apps/*.yaml` 파일에서 확인할 수 있으며, Sync Wave는 `argocd.argoproj.io/sync-wave` 어노테이션과 동일합니다.

| Wave | Path | 목적 |
|------|------|------|
| 02 | `namespaces/{base,dev,prod}` | 비즈니스/데이터/플랫폼 Namespace 정의 |
| 03 | `rbac-storage/{base,dev,prod}` | ServiceAccount, ClusterRole, dockerhub-secret, `gp3` StorageClass |
| 06 | `network-policies/{base,dev,prod}` | Tier 기반 기본 차단 + 허용 정책 |
| 11 | `secrets/external-secrets/{base,dev,prod}` | SSM Parameter / Secrets Manager → Kubernetes Secret |
| 60 | `apis/<domain>/{base,env}` | 도메인별 Deployment/Service/ConfigMap 템플릿 |
| 70 | `ingress/{base,env}` | API / ArgoCD / Grafana Ingress + ExternalDNS annotation |

> 데이터 CR(`platform/cr/**`)과 CRD(`platform/crds/**`)는 플랫폼 계층에서 관리하며, Helm 리소스는 모두 `clusters/{env}/apps/*.yaml`의 upstream chart 정의를 사용합니다.

## 로컬 검증 예시

```bash
# Namespaces (dev)
kustomize build workloads/namespaces/dev

# NetworkPolicy (prod)
kustomize build workloads/network-policies/prod

# 특정 API (auth, dev)
kustomize build workloads/domains/auth/dev
```

## 새 API 도메인 추가 절차
1. `workloads/domains/<domain>/base/` scaffolding 복사 → Deployment/Service/ConfigMap 작성
2. `workloads/domains/<domain>/{dev,prod}/kustomization.yaml`에서 base 참조 후 patch 추가
3. 필요한 NodeSelector/taint, Secret 참조(ExternalSecret), ConfigMap 등을 patch 파일에 정의
4. `clusters/{env}/apps/60-apis-appset.yaml` 또는 해당 ApplicationSet 리스트에 새 도메인 경로를 추가
5. `argocd app diff` → `argocd app sync`로 반영

## 참고
- 플랫폼 Helm 리소스: `clusters/{env}/apps/1*-*.yaml` (upstream chart 정의)
- 문제 발생 시 `docs/troubleshooting/TROUBLESHOOTING.md`와 `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md` 내 Kustomize/Namespace 섹션을 참고하세요.
- 민감 값은 Terraform → SSM → ExternalSecret 경로로 주입되며, Kustomize 템플릿에는 literal 비밀번호를 두지 않습니다.
