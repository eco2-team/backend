# CI/CD 리팩터링 계획 (Helm + Kustomize + Argo CD)

> **목적**: 현재 GitHub Actions 워크플로(“CI Quality Gate”, “Infrastructure Bootstrap”)를 Helm Operator/Monitoring/ALB + Kustomize Namespace/NetworkPolicy/API + ArgoCD App-of-Apps 조합에 맞춰 고도화하기 위한 기준 문서.  
> **대상 워크플로**: `.github/workflows/ci-quality-gate.yml`, `.github/workflows/infrastructure-bootstrap.yml`

---

## 1. 현행 상태 요약

| 워크플로 | 주요 기능 | 비고 |
|----------|-----------|------|
| **CI Quality Gate** | - Terraform fmt/validate<br>- Helm lint(일부 차트)<br>- Kustomize 스모크 빌드<br>- 서비스 코드 품질(black/ruff/pytest) + GHCR 빌드/푸시 | Helm 설치 테스트, Kustomize 스키마 검증, ArgoCD 렌더 정합성 미보장 |
| **Infrastructure Bootstrap** | - workflow_dispatch 기반 수동 실행<br>- Terraform apply + (선택) Ansible bootstrap → Root App 적용 | CI 내 Ansible 호출은 제거 예정, 오프라인 가이드(`docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md`)로 대체 |

---

## 2. 강화 목표 (Why)

1. **Helm 차트 안정성**: chart-testing(=ct)로 lint + Kind install 테스트 → Operator/모니터링/ALB 차트 변경 시 실제 설치 결과 검증.  
2. **Kustomize 정합성**: `kubeconform` 으로 스키마/CRD 검사, 필요 시 `kyverno` 정책 검사 → Namespace/NetworkPolicy/API 오버레이 품질 확보.  
3. **ArgoCD 렌더 일치**: CMP(Helm→Kustomize)와 동일 명령을 CI에서 실행해 “CI 산출물 = ArgoCD 배포물” 보장.  
4. **Server-side Dry-run(선택)**: Kind + CRD 선적용 후 `kubectl apply --server-side --dry-run=server` 로 API 스키마/머지 충돌 조기 탐지.  
5. **ApplicationSet 템플릿 검증**: `argocd appset generate` 로 생성 Application을 CI에서 사전 확인.  
6. **Ansible 제거**: GitHub Actions에서 Ansible 단계 삭제, 부트스트랩 문서만 유지.

---

## 3. 타깃 CI 구조

```
jobs:
  terraform          # fmt / validate / (선택) plan
  helm-ct            # ct lint + ct install (Kind)
  kustomize-validate # kustomize build → kubeconform (+ kyverno)
  render-parity      # CMP 명령 (helm→kustomize)로 렌더, artifact 업로드
  server-dry-run     # Kind + CRD → kubectl apply --server-side --dry-run=server
  appset-verify      # argocd appset generate 로 Application 목록 검증
  api-quality        # black / ruff / pytest (변경 서비스만)
  api-build-push     # docker buildx + GHCR (변경 서비스만)
```

- **paths 필터**로 Helm/Kustomize/서비스 별 변경 감지 → 필요한 잡만 실행.  
- `render-parity` 결과는 아티팩트로 업로드하여 ArgoCD Diff 조사 시 재활용.  
- `server-dry-run` / `appset-verify` 는 옵션이지만, Sync Wave 복잡도가 높아질수록 추천.

---

## 4. 구현 단계

| 단계 | 작업 내용 | 파일/도구 |
|------|-----------|-----------|
| 1 | ct 설정 추가 (`charts/ct.yaml`), Helm 차트 경로 정리 | helm/chart-testing-action, helm/kind-action |
| 2 | Kustomize 빌드 매트릭스 정의(dev/prod 등), kubeconform 설치 스크립트 작성 | kustomize 5.x, kubeconform, Datree CRD catalog |
| 3 | Kind에서 실행 가능한 Stub Chart + ct 구성 (`charts/testing/**`) | chart-testing lint/install, AWS 의존 차트 모의 검증 |
| 4 | CMP 명령 스크립트화 (`scripts/render-like-argocd.sh`) 후 CI/Argo에서 공유 | kustomize --enable-helm 또는 Helm→Kustomize 체인 |
| 5 | Kind + CRD 프리로드 스크립트 작성 (`scripts/ci/server-dry-run.sh`) | kubectl apply --server-side --dry-run=server |
| 6 | ApplicationSet 템플릿 검증 단계 추가 (`argocd appset generate`) | argocd/argocd:v2.x 컨테이너 |
| 7 | `.github/workflows/infrastructure-bootstrap.yml` 에서 Ansible step 제거, 문서 링크만 유지 | docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md |
| 8 | `docs/refactor/gitops-sync-wave-TODO.md` 및 관련 README 업데이트 | 진행 상황 추적 |

---

## 5. 향후 참고 링크

- `docs/ci-cd/GITHUB_ACTIONS_CI_QUALITY_GATE.md`: 기존 품질 게이트 세부 가이드  
- `docs/deployment/LOCAL_CLUSTER_BOOTSTRAP.md`: Terraform → Ansible → ArgoCD 로컬 부트스트랩 절차  
- `docs/architecture/operator/OPERATOR_SOURCE_SPEC.md`: Helm Operator 소스/버전 기준  
- `docs/refactor/gitops-sync-wave-TODO.md`: v0.7.4 진행 상황 체크리스트

> 위 계획을 README에 기록한 후, 워크플로 리팩터링을 순차적으로 적용한다. 변경 시 README를 함께 갱신해 CI/CD 설계 변화를 추적한다.


