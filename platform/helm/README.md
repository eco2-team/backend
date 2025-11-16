# Platform Helm Charts (벤더 스택)

이 디렉터리는 외부 Helm chart를 ArgoCD Multi-Source 패턴으로 배포하기 위한 ApplicationSet과 환경별 values를 보관한다.

## Multi-Source 패턴

```yaml
sources:
  - repoURL: https://prometheus-community.github.io/helm-charts  # 공식 Chart
    chart: kube-prometheus-stack
    targetRevision: 56.21.1
  - repoURL: https://github.com/SeSACTHON/backend.git          # Values 전용
    targetRevision: HEAD
    ref: values                                                # $values로 참조
helm:
  valueFiles:
    - $values/platform/helm/kube-prometheus-stack/values/dev.yaml
```

### 장점
1. **Chart 분리**: 공식 Helm repo를 upstream으로 유지하고 values만 Git 관리
2. **버전 추적**: Chart 업그레이드 시 `targetRevision`만 변경하면 되고 values는 별도 이력 유지
3. **환경 분리**: dev/prod values를 동일 구조로 관리하며 ApplicationSet이 자동 매핑

## 디렉터리 구조

각 컴포넌트는 아래 규칙을 따른다:

```
platform/helm/<component>/
├─ app.yaml                    # ArgoCD ApplicationSet (Wave 명시)
└─ values/
   ├─ dev.yaml                 # Dev 환경 values
   └─ prod.yaml                # Prod 환경 values
```

- `app.yaml`: ApplicationSet generators로 dev/prod를 리스트하고, `{{env}}`, `{{valueFile}}` 변수로 자동 매핑
- `values/{env}.yaml`: Helm chart의 `values.yaml`을 override하는 환경별 설정

## 주의사항

1. **Secret 참조**: values 파일에 민감 정보를 직접 넣지 말고, `existingSecret`으로 ExternalSecrets 출력을 참조한다.
2. **CRD 선행**: `platform/crds/` 경로의 CRD를 Wave -1에서 먼저 적용해야 Operator Helm이 정상 동작한다.
3. **Sync Wave**: `app.yaml`의 `argocd.argoproj.io/sync-wave` 어노테이션이 `ARGOCD_SYNC_WAVE_PLAN.md`와 일치해야 한다.

---

> 새 Helm 컴포넌트를 추가할 때는 위 구조를 따르고, `OPERATOR_SOURCE_SPEC.md`에 소스와 버전을 먼저 기록한 뒤 app.yaml과 values를 생성한다.
