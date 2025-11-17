# Sync Wave 점검 체크리스트

> 목적: Argo CD Root-App을 신규 환경/브랜치에서 실행하기 전에 **Helm / Kustomize / Argo CD** 관점의 필수 확인 항목을 한 번에 점검해 OutOfSync·순서 꼬임을 예방한다.

## 1. 공통 (SSOT & Argo CD)
- [ ] `clusters/README.md`의 Wave 표와 실제 `clusters/{env}/apps/*.yaml` 구성(Wave 번호·파일명·Source Path)이 완전히 일치한다.
- [ ] `clusters/{env}/root-app.yaml`의 `targetRevision`이 환경 정책(예: dev → 작업 브랜치, prod → main)과 동일하고, 하위 Application에서도 같은 브랜치를 바라본다.
- [ ] 새 Wave 파일 추가 시 README 갱신 여부를 PR 체크리스트에 포함했는지 확인한다.
- [ ] `scripts/ci/lint-appset-templates.sh`로 ApplicationSet 템플릿에서 literal 따옴표(`"{{name}}"`)가 없는지 CI에서 강제한다.

## 2. Helm 모듈 점검
- [ ] `platform/helm/<component>/app.yaml`은 **multi-source** 패턴을 따르고 `values` 소스의 `targetRevision`이 환경별 브랜치 변수(`{{targetRevision}}`)로 정의되어 있다.
- [ ] 각 Helm Application(예: `05-calico.yaml`, `15-alb-controller.yaml`)은 `directory.include: app.yaml`을 사용해 values 파일이 매니페스트로 렌더되지 않도록 한다.
- [ ] `platform/helm/<component>/values/{env}.yaml`이 실제 존재하며, 참조 경로(`valueFile`)가 동일하다.
- [ ] External chart 버전(`targetRevision`)이 CRD/Operator 버전과 호환되는지 사전 검증한다.
- [ ] ExternalDNS는 `external-dns.alpha.sesacthon.io/managed-by=external-dns`가 붙은 Ingress/Service만 관리하며, Apex/Alias 레코드는 Terraform·Ansible(Route53)에서만 관리된다.

## 3. Kustomize(workloads) 점검
- [ ] 모든 경로가 `base/` + `{env}/` 오버레이 구조를 가지며, `kustomization.yaml`이 base를 참조한다.
- [ ] Wave 표에 없는 중복 Application(dev에서 Wave 0/3에 동시에 선언 등)이 존재하지 않는다.
- [ ] `workloads/apis/<service>/{env}` 디렉터리가 `60-apis-appset`의 generator 리스트와 1:1 대응한다.
- [ ] 민감 값은 ExternalSecret/ConfigMap을 통해 주입되고, Kustomize에 literal secrets가 남아있지 않다.

## 4. CRD / Secrets 선행 조건
- [ ] Wave 0 `00-crds.yaml`이 성공해야 하는 모듈(ESO, Prometheus, Postgres 등)을 명시하고, 실패 시 뒤 Wave를 pause하는 운영 플랜을 갖고 있다.
- [ ] Wave 10(ESO Helm) → Wave 11(ExternalSecret CR) → Wave 15+ (ALB, API 등) 의존 순서가 README와 동일하며, 선행 Wave 실패 시 즉시 탐지할 수 있는 Alert/대시보드를 구성한다.
- [ ] `scripts/diagnostics/check-wave-health.sh <env>`를 이용해 Wave 0/10/11 애플리케이션(`*-crds`, `*-external-secrets`, `*-secrets`)이 Healthy+Synced인지 확인한다.

## 5. 운영 시나리오 체크
- [ ] Root-App Sync 전 `argo cd app diff`로 대규모 변경을 미리 확인한다.
- [ ] Helm chart나 Operator 버전을 올릴 때는 platform/helm, platform/crds, workloads 문서를 동시에 업데이트한다.
- [ ] 신규 env 생성 시 `clusters/{env}` 복제 후 `project`/`namespace`/`path`/`targetRevision`을 일괄 검증한다.
- [ ] Route53(Infra)와 ExternalDNS(앱 Ingress) 관리 범위를 명확히 문서화하고, ExternalDNS annotation filter 설정이 최신인지 확인한다.

> 이 문서를 기준으로 브랜치 이동, 신규 Wave 추가, 환경 복제 작업 전후에 최소 한 번씩 체크하면 다른 GPT/사용자 간 구조 평가 시에도 동일한 기준을 공유할 수 있다.

