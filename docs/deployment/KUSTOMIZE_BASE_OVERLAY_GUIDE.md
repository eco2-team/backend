# Kustomize Base/Overlay 구조 가이드

> **참고 레퍼런스**  
> - CNCF SIG App Delivery, *“Kubernetes Style Guide”* (base ↔ overlay 계층 권장)  
> - Kustomize 공식 문서: [https://kubectl.docs.sesacthon.io/references/kustomize/kustomization/](https://kubectl.docs.sesacthon.io/references/kustomize/kustomization/)  
> - Argo CD Best Practice: base 디렉토리에 공통 리소스를 정의하고 환경별 overlay를 Application으로 배포

---

## 1. Base vs Overlay 개념

| 항목 | Base | Overlay |
|------|------|---------|
| 목적 | 공통 리소스 템플릿, 재사용 가능한 기본값 | 환경(dev/staging/prod)별 차별화, 팀별 패치 |
| 구성 요소 | `kustomization.yaml`, 공통 Deployment/Service/ConfigMap | `kustomization.yaml` + patchesStrategicMerge/patches/vars |
| 배포 방식 | 다른 Kustomize root에서 `bases` 또는 `resources`로 포함 | ArgoCD Application / CLI에서 `kustomize build overlays/prod` |
| 변경 범위 | 구조적 변동 적음, 버전 관리 엄격 | 환경에 맞는 Replica, Ingress host, Secret 참조 등 가변 |

즉, Base는 “변하지 않는 스캐폴드”, Overlay는 “환경/도메인별 패치 집합”이다.

---

## 2. Patch 개념

Kustomize overlay는 세 가지 방식으로 Base를 수정한다.

1. **patchesStrategicMerge**: Kubernetes 오브젝트에 특화된 Merge (Deployment spec.template.spec.containers 등).  
2. **patchesJson6902**: JSON patch 표준. 복잡한 구조 변경 시 사용.  
3. **replacements / variables**: 특정 필드를 동적으로 치환.

예시 (auth API에 prod overlay 적용):

```yaml
# overlays/prod/kustomization.yaml
resources:
  - ../../base
patchesStrategicMerge:
  - replica-patch.yaml
  - env-secretref.yaml

# overlays/prod/replica-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-api
spec:
  replicas: 4   # prod만 4 replicas
```

---

## 3. 디렉토리 구조 (권장)

```
workloads/
├─ namespaces/
│  ├─ base/
│  └─ overlays/(dev|prod)/
├─ network-policies/
│  ├─ base/          # deny-all + 공통 허용
│  └─ overlays/(dev|prod)/
├─ data/
│  ├─ postgres/overlays/(dev|prod)/PostgresCluster.yaml
│  └─ redis/overlays/(dev|prod)/RedisCluster.yaml
├─ monitoring/
│  ├─ prometheus/
│  └─ grafana/
├─ ingress/
│  ├─ ingressclassparams/
│  └─ apps/
├─ secrets/
│  ├─ external-secrets/
│  └─ sops/
└─ apis/
   ├─ auth/overlays/(dev|prod)/
   ├─ my/overlays/(dev|prod)/
   └─ ...
projects/
└─ ... (Argo CD Project 등)
```

### 적용 원칙
1. Base 디렉토리는 공통 라벨, 어노테이션, 기본 매니페스트를 포함.  
2. Overlay는 `namespace`, `network-policies`, `apis` 등 책임 단위로 분리 해 Git diff가 명확하도록 구성.  
3. ArgoCD는 overlay를 단일 Application으로 등록하고, Sync Wave는 `ARGOCD_SYNC_WAVE_PLAN.md`에 따름.

---

## 4. Patch 전략

| 시나리오 | 권장 Patch |
|----------|------------|
| Replica/Resource 변경 | `patchesStrategicMerge` |
| Ingress host, domain 변경 | ConfigMap/Ingress patch |
| Secret 이름/ARN 주입 | patchesStrategicMerge 또는 `replacements` |
| Operator CR (예: PostgresCluster) minor 차이 | Overlay 내에서 `values-dev.yaml` 등으로 분리 |

Patch 파일은 overlay 디렉토리 루트에 두고, `kustomization.yaml`에 명시한다. 여러 패치가 있을 경우 파일명을 기능별로 나눠 추적성을 높인다(`replica.yaml`, `node-selector.yaml` 등).

---

## 5. GitOps와의 연계

1. **ArgoCD Application**  
   - `repoURL`: 이 저장소  
   - `path`: `workloads/domains/auth/overlays/prod`  
   - `annotations.argocd.argoproj.io/sync-wave`: 서비스 계층에 맞춰 설정

2. **프로모션**  
   - Dev overlay에 변경 → Staging overlay cherry-pick → Prod overlay  
   - Base 변경 시 모든 overlay가 영향을 받으므로 PR 템플릿에 “Base 영향” 항목을 추가.

3. **검증**  
   - `kustomize build workloads/domains/auth/overlays/prod | kubectl apply --dry-run=client -f -`  
   - CI에서 overlay별 build 를 수행해 Drift 감지.

---

## 6. FAQ

- **Base에서 환경 값을 정의해도 되나요?** → 불가. Base는 공통값만 포함하고, 환경 값은 overlay patch로 관리.  
- **Overlay 간 중복이 많다** → `workloads/common-patches`를 만들고 `resources`로 공유하거나, Helm chart를 병행 검토.  
- **Patch 순서가 충돌한다** → patchesStrategicMerge는 YAML 수평 병합, JSON patch는 순차 적용이므로 의존성이 있을 경우 파일명에 `01-` prefix를 부여.

---

> 위 구조와 패치 원칙을 지키면, 외부 기여자가 base/overlay의 의미를 혼동하지 않고 기여할 수 있으며, ArgoCD나 다른 GitOps 도구에서도 일관된 배포 전략을 유지할 수 있다.

