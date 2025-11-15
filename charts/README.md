# Charts Directory – Helm + Kustomize 하이브리드 전략

`charts/` 는 Kustomize로 표현하기 어려운 모듈(관찰 계층, 데이터 계층, 플랫폼 서비스)을 Helm으로 관리하기 위한 공간입니다.  
APP-OF-APPS-DECISION.md 기준으로 다음과 같이 병행 운용합니다.

| Wave | 대표 리소스 | 패키징 | 경로 |
|------|-------------|--------|------|
| 0~1  | Namespaces, NetworkPolicies | Kustomize | `k8s/foundations`, `k8s/infrastructure` |
| 20   | AWS Load Balancer Controller | Helm | `eks/aws-load-balancer-controller` (external) |
| 40   | kube-prometheus-stack, Grafana | Helm | `charts/observability/kube-prometheus-stack` |
| 60   | PostgreSQL, Redis, RabbitMQ | Helm | `charts/data/databases` |
| 70   | Atlantis (Terraform GitOps) | Helm | `charts/platform/atlantis` |
| 80+  | API 마이크로서비스 | Kustomize overlays | `k8s/overlays/<domain>` |

## 현재 포함된 Helm Chart

### 1. `observability/kube-prometheus-stack`
- kube-prometheus-stack 의존성을 포함한 Umbrella Chart  
- ArgoCD `apps/40-monitoring.yaml`에서 Helm 모드로 사용  
- values에 노드 셀렉터/토러런스/스토리지 요구사항을 반영

동기화 방법:
```bash
cd charts/observability/kube-prometheus-stack
helm dependency build
```

### 2. `data/databases`
- PostgreSQL, Redis, RabbitMQ를 한 번에 배포하는 Umbrella Chart  
- ArgoCD `apps/60-data-clusters.yaml`에서 사용  
- 민감 값은 상위 values 파일이나 Secret으로 override

```bash
cd charts/data/databases
helm dependency build
```

### 3. `platform/atlantis`
- Terraform PR 자동화를 담당하는 Atlantis Chart  
- ArgoCD `apps/70-gitops-tools.yaml`이 `helm` 소스로 참조  
- values에서 repo allowlist, tolerations, NodePort 등을 제어

```bash
cd charts/platform/atlantis
helm template .
```

## 새로운 Chart를 추가하려면?
1. `charts/<wave>/<component>/` 디렉터리 생성  
2. `Chart.yaml`에 의존성/메타데이터 정의  
3. `values.yaml`에 기본값 기술 (민감 정보는 별도 values/Secret 사용)  
4. `argocd/apps/<wave>-*.yaml`의 `source.helm` 설정을 갱신  

```yaml
source:
  repoURL: https://github.com/SeSACTHON/backend
  targetRevision: develop
  path: charts/<wave>/<component>
  helm:
    releaseName: <component>
```

## FAQ
- **Helm과 Kustomize를 함께 쓰는 이유?**  
  CRD/Hook가 많은 관찰·데이터 계층은 Helm이 유지보수 비용이 낮습니다. 네임스페이스/네트워크 정책/마이크로서비스 등은 Kustomize로 표현합니다.

- **values 보안은?**  
  공통 기본값만 저장하고, 환경별 민감 정보는 `values.<env>.yaml`이나 ExternalSecret으로 주입합니다.

---

**마지막 업데이트**: 2025-11-16  
**담당자**: EcoEco Backend Team (Helm/Kustomize Mixed Strategy)
