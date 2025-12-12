## Platform CRDs

`platform/crds/` 디렉터리는 Wave 00 시점에 필요한 **모든 CustomResourceDefinition**을 한 번에 적용하기 위한 Kustomize 번들입니다. Helm/Operator App에서는 `skipCrds: true` 또는 patch로 CRD 생성을 제거하고, 이 디렉터리만이 단일 진실(SSOT)이 되도록 유지합니다.

### 디렉터리 구조
- `base/kustomization.yaml`
  - AWS Load Balancer Controller CRD
  - External Secrets Operator CRD
  - Redis Operator CRD (`redis`, `redisclusters`, `redisreplications`, `redissentinels`)
  - Postgres Operator CRD (`postgresql`, `operatorconfiguration`)
  - Prometheus Operator CRD (Alertmanager / ServiceMonitor / Thanos 등)
- `{env}/kustomization.yaml` : base를 참조하고 환경별 CRD patch를 추가합니다.
- `{env}/patches/external-secrets-*.yaml` : External Secrets conversion webhook가 해당 환경의 Helm Release 서비스명(`{env}-external-secrets-webhook`)을 바라보도록 덮어씁니다.

### 배포 순서
1. `kubectl apply -k platform/crds/{env}` 로 CRD를 적용합니다.
2. 이후 Wave 10, 15, 16, 20, 21, 24, 28 Helm App에서는 `skipCrds` 옵션이 설정되어 있으므로 중복 생성이 발생하지 않습니다.
3. CR 버전을 업그레이드할 때는 **base**의 URL을 교체한 뒤, 각 env patch에서 webhook service 이름/네임스페이스가 올바른지 확인합니다.

### 새로운 CRD 추가 시 체크리스트
- [ ] upstream `raw.githubusercontent.com` 또는 chart repository URL을 base `resources`에 추가한다.
- [ ] 해당 CRD를 소비하는 Helm/App에서 CRD 생성을 비활성화한다 (`skipCrds`, patch 등).
- [ ] 웹훅/네임스페이스/라벨이 환경마다 다르면 `{env}/patches/`에 JSON6902/Strategic Merge patch를 추가한다.
- [ ] `clusters/{env}/apps/00-crds.yaml` 의 `targetRevision`이 현재 branch/tag를 가리키는지 확인한다.

### 적용 예시
```bash
# dev 환경
kubectl apply -k platform/crds/dev

# prod 환경
kubectl apply -k platform/crds/prod
```

> External Secrets Operator는 conversion webhook 서비스명이 Helm Release 이름에 종속되므로, env patch를 누락하면 `conversion webhook failed` 오류가 발생합니다.
