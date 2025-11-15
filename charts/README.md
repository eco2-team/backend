# Charts Directory – Helm + Kustomize 하이브리드 전략

`charts/` 는 **APP-OF-APPS-DECISION.md**에서 정의한 것처럼, Kustomize로 표현하기에 비효율적인 모듈(관찰/데이터 레이어 등)을 Helm으로 관리하기 위한 공간입니다.  
Kustomize와 Helm은 다음 원칙으로 병행 운용합니다.

| 계층(Wave) | 대표 리소스 | 패키징 방식 | 소스 경로 |
|-----------|-------------|-------------|-----------|
| Wave 0~1  | Namespaces, NetworkPolicies | **Kustomize** | `k8s/infrastructure` |
| Wave 2    | kube-prometheus-stack, Grafana | **Helm** | `charts/observability/kube-prometheus-stack` |
| Wave 3    | PostgreSQL, Redis, RabbitMQ (예정) | **Helm** | `charts/data/*` (추가 예정) |
| Wave 4    | Atlantis (Terraform GitOps) | **Helm** | `charts/platform/atlantis` |
| Wave 5    | API 마이크로서비스 | **Kustomize overlay** | `k8s/overlays/<domain>` (재구성 중) |

> 📘 상세한 의사결정과 Wave 정의는 `docs/architecture/APP-OF-APPS-DECISION.md` 를 참고하세요.

---

## 현재 포함된 Helm Chart

### 1. `observability/kube-prometheus-stack`
- kube-prometheus-stack 종속성을 포함한 Umbrella Chart
- ArgoCD `apps/30-monitoring.yaml` 에서 `helm` 소스로 사용
- `values.yaml` 에는 Ansible로 운영하던 리소스 요구사항/노드 셀렉터/토러런스를 그대로 반영
- 민감 값(예: Grafana Admin Password)은 **오버레이 values 파일** 또는 **Secret** 으로 덮어써야 합니다.

Helm dependency를 동기화해야 할 때:
```bash
cd charts/observability/kube-prometheus-stack
helm dependency build
```

### 2. `data/databases`
- PostgreSQL/Redis/RabbitMQ를 한 번에 배포하는 Umbrella Chart
- Bitnami Chart를 의존성으로 사용하며, 기본 리소스/토러런스/스토리지 요구사항을 Wave 30 스펙에 맞춰 정의
- 비밀번호 등 민감 값은 `values.<env>.yaml` 혹은 Secret으로 반드시 덮어써야 함

Dependency 동기화:
```bash
cd charts/data/databases
helm dependency build
```

### 3. `platform/atlantis`
- Terraform PR 자동화를 담당하는 Atlantis를 Helm 패키지로 관리
- ArgoCD `apps/20-platform.yaml`에서 `helm` 소스로 사용하며, Secret(`atlantis-secrets`)은 외부에서 주입
- NodePort/StatefulSet, kubectl init container, ConfigMap 기반 repo-workflow 설정을 values로 제어

배포 방법:
```bash
cd charts/platform/atlantis
helm template .
```

---

## 새로운 Helm 모듈을 추가하려면?
1. `charts/<wave>/<component>/` 디렉터리를 생성
2. `Chart.yaml` 안에 외부 dependency 또는 로컬 템플릿을 정의
3. `values.yaml` 에 환경 기본값을 기술하고, 민감 정보는 Secret/ExternalSecret 으로 우회
4. `argocd/apps/<wave>-*.yaml` 의 `source` 를 Helm 모드로 설정하여 App of Apps 파이프라인에 편입

예시:
```yaml
source:
  repoURL: https://github.com/SeSACTHON/backend
  targetRevision: develop
  path: charts/data/postgresql
  helm:
    releaseName: postgresql
```

---

## FAQ
- **Q. 왜 Helm을 다시 사용하나요?**  
  Kustomize만으로는 업스트림 차트의 CRD/Hook/템플릿을 모두 복제해야 하므로 유지보수가 어렵습니다. Helm으로 Observability·Data 계층을 관리하면 ArgoCD에서 바로 버전을 추적할 수 있습니다.

- **Q. values 보안은 어떻게 처리하나요?**  
  공통 기본값은 `values.yaml` 에 남기고, 환경별 민감 값은 `values.<env>.yaml` 혹은 ExternalSecret으로 주입합니다.

---

**최종 업데이트**: 2025-11-15  
**담당**: EcoEco Backend Team (Helm/Kustomize Mixed Strategy)
