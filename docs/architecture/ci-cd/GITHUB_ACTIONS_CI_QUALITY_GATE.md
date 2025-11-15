# GitHub Actions CI 품질 게이트 가이드

- **작성일**: 2025-11-15  
- **대상**: `develop` / `main` 브랜치, GitOps 기반 CD(ArgoCD App-of-Apps)  
- **목적**: CD 파이프라인(ArgoCD)과 호응하는 CI 품질 게이트 정의 및 GitHub Actions 구현 원칙 정리

---

## 1. CD 파이프라인 맥락 요약

| 구분 | 현행 구성 | CI에서 보장해야 할 품질 신호 |
|------|-----------|-----------------------------|
| GitOps Root | `argocd/root-app.yaml`, `targetRevision: develop` | `develop` 브랜치의 매니페스트가 항상 빌드 가능해야 함 |
| 패키징 | Kustomize(Infra/Platform/API) + Helm(Observability/Data) 혼합 | `kustomize build`, `helm lint`, dependency update가 사전에 검증돼야 함 |
| 인프라 | Terraform + Ansible (수동/Atlantis) | 코드 포맷·유효성 검증 후에만 PR/머지 허용 |
| 배포 파이프라인 | Terraform → Ansible → ArgoCD Sync | CI에서 IaC/매니페스트 품질 신호를 만들어 CD 실패를 사전 차단 |

---

## 2. 베스트 프랙티스

### 2.1 품질 게이트 구성

| 단계 | 도구 / 액션 | 목적 |
|------|-------------|------|
| Commit 타입 필터 | Conventional commit prefix 파싱 → `chore`, `docs` 등은 CI 스킵 | 불필요한 리소스 소모 최소화, 의도적 Skip 정책 명시화 |
| Terraform 포맷/검증 | `terraform fmt -check`, `terraform init -backend=false`, `terraform validate` | Atlantis/수동 CD 이전에 정적 오류 탐지 |
| Helm 차트 검증 | `helm dependency update` + `helm lint --strict` (Observability/Data Waves) | Chart 템플릿/values 유효성 보증 → ArgoCD Helm Source 안정화 |
| Kustomize 스모크 테스트 | `kustomize build` (Infra, Data Operators, API Overlays) | GitOps에서 바로 적용 가능한 매니페스트만 `develop`에 머지 |
| API 품질 검사 | `black --check`, `ruff check`, `pytest` | 서비스 코드 린트/포맷/테스트를 커밋 단계에서 보장 |
| 컨테이너 이미지 빌드/푸시 | `docker/build-push-action@v5` & GHCR | 변경된 API 이미지를 자동으로 빌드해 GHCR(`ghcr.io/sesacthon/<service>-api`)에 업로드 |

### 2.2 CD와의 연계 포인트

1. **동일 브랜치 기준**: CI는 `develop`/`main`에서만 실행 → ArgoCD Root App과 동일 기준 유지.  
2. **Manifest Validation → Sync 안정성**: Helm/Kustomize lint가 성공해야만 CD에서 Sync 재시도가 의미있음.  
3. **IaC Static Validation**: Terraform/Ansible 문제를 PR 단계에서 차단해, 운영 환경 파괴적 변경을 미리 잡는다.  
4. **Skip 정책의 명문화**: 사소한 문서/관리성 변경(chore, docs)은 CI를 건너뛰되, Step Summary에 기록하여 Reviewer가 맥락을 이해하도록 한다.

---

## 3. 워크플로 설계 개요

```text
commit-filter (chore/docs 여부) ─┬─> skip-notice (요약만 남김)
                                 │
                                 └─> quality-gate (Terraform / Helm / Kustomize)
                                         ↓
                                 detect-api-changes (services/** diff)
                                         ↓
                         ┌───────────────┴───────────────┐
                         │                               │
                 api-quality (black/ruff/pytest)   api-build-push (GHCR)
```

- **commit-filter Job**  
  - PR 제목 또는 Push 커밋 메시지를 Conventional Commit 규칙으로 파싱.  
  - `chore`, `docs` 유형은 `skip=true` 로 지정해 모든 후속 Job을 생략한다.

- **quality-gate Job**  
  - Terraform fmt/validate, Helm lint, Kustomize build를 실행해 GitOps 매니페스트 유효성을 확보한다.

- **detect-api-changes Job**  
  - `tj-actions/changed-files` 로 `services/**` 경로를 스캔, 변경된 서비스 목록(JSON)과 `has_changes` 플래그를 출력한다.

- **api-quality Job**  
  - 변경된 서비스만 matrix로 분기해 `black --check`, `ruff check`, `pytest` 를 실행한다.  
  - 서비스별 `requirements.txt` 를 설치해 실제 런타임과 동일한 의존성으로 품질 검사를 수행한다.

- **api-build-push Job**  
  - 품질 검사를 통과한 서비스만 Docker 이미지를 빌드.  
  - `docker/build-push-action` 으로 `ghcr.io/sesacthon/<service>-api:{GITHUB_SHA,latest}` 두 태그를 동시에 업로드한다.

- **skip-notice Job**  
  - CI가 건너뛰어진 경우 Step Summary에 이유와 커밋 타입을 기록한다.

---

## 4. 스킵 정책 상세

| 타입 | 적용 규칙 | 근거 |
|------|-----------|------|
| `chore:*` | 저장소 메타 작업 (예: 이슈 템플릿 수정, CI 구성 파일 이동) | 배포 산출물에 영향이 없고, Reviewer가 의도적으로 skip 가능 |
| `docs:*` | 문서만 수정 (아키텍처 노트, README 갱신) | GitOps 리소스에 영향이 없으므로 런너 리소스 절약 |
| 기타 (feat, fix, refactor 등) | CI **무조건 실행** | Kubernetes/ArgoCD에 영향을 줄 가능성 존재 |

> 필요 시 `ci:force` 라벨 또는 커밋 메시지에 `!ci` 키워드를 확장하도록 여지를 남겨둔다.

---

## 5. 구현 상태

- 워크플로 파일: `.github/workflows/ci-quality-gate.yml`  
- 포함 검사: Terraform fmt/validate, Helm lint(Observability/Data), Kustomize build(Infra/API), API별 black/ruff/pytest.  
- 컨테이너: 변경된 API 디렉터리만 Docker Buildx로 빌드 후 GHCR(`sesacthon/<service>-api`)에 SHA/Latest 태그로 업로드.  
- Skip 정책: `chore:*`, `docs:*` Conventional Commit prefix 자동 감지.  
- 레거시 CI 정의(`infrastructure-old.yml.backup`)는 제거해 충돌을 방지했다.

앞으로 다중 환경 values Override, SonarQube/coverage 리포트 등을 추가할 때도 이 구조 위에서 확장하면 된다.

