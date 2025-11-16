# `workloads/` 개요

`workloads/` 디렉터리는 **Helm으로 관리하지 않는 모든 Kubernetes 리소스**(Namespace, RBAC, NetworkPolicy, ExternalSecret, API Deployment 등)를 Kustomize로 정의합니다.  
Argo CD App-of-Apps가 참조하는 경로는 `clusters/{env}/apps/*.yaml` 파일에서 확인할 수 있으며, Sync Wave는 `argocd.argoproj.io/sync-wave` 어노테이션과 동일합니다.

| Wave | Path | 목적 |
|------|------|------|
| 0 / 2 | `namespaces/{base,dev,prod}` | 비즈니스/데이터/플랫폼 네임스페이스 정의 |
| 3 | `rbac-storage/{base,dev,prod}` | 공통 ServiceAccount, ClusterRole, StorageClass |
| 5-6 | `network-policies/{base,dev,prod}` | Tier 기반 기본 차단 + 허용 정책 |
| 11 | `secrets/external-secrets/{base,dev,prod}` | SSM → Kubernetes Secret 동기화 (ExternalSecrets CR) |
| 20+ | `ingress/apps/{base,env}` | ALB Ingress, ExternalDNS annotation, 환경별 인증서 |
| 35 | `data/postgres/*`, `data/redis/*` | Operator가 소비할 Postgres/Redis CR 선언 |
| 60 | `apis/<domain>/{base,env}` | 각 API Deployment/Service/ConfigMap/Secret 템플릿 |

> Helm Chart는 `platform/charts/**`에서 관리합니다. (예: Calico, ALB Controller, kube-prometheus-stack 등)

## 로컬 검증 예시

```bash
# Namespaces (dev)
kustomize build workloads/namespaces/dev

# NetworkPolicy (prod)
kustomize build workloads/network-policies/prod

# 특정 API (auth, dev)
kustomize build workloads/apis/auth/dev
```

## 새 API 도메인 추가 절차
1. `workloads/apis/<domain>/base/` scaffolding 복사 → Deployment/Service/ConfigMap 작성  
2. `workloads/apis/<domain>/{dev,prod}/kustomization.yaml`에서 base 참조 후 patch 추가  
3. 필요한 NodeSelector/taint, Secret 참조(ExternalSecret), ConfigMap 등을 patch 파일에 정의  
4. `clusters/{env}/apps/60-apis-appset.yaml` 또는 해당 ApplicationSet 리스트에 새 도메인 경로를 추가  
5. `argocd app diff` → `argocd app sync`로 반영

## 참고
- Helm 리소스: `platform/charts/<component>/app.yaml` (Argo CD ApplicationSet/Helm values)  
- 문제 발생 시 `docs/TROUBLESHOOTING.md`와 `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md` 내 Kustomize/Namespace 섹션을 참고하세요.  
- 민감 값은 Terraform → SSM → ExternalSecret 경로로 주입되며, Kustomize 템플릿에는 literal 비밀번호를 두지 않습니다.

