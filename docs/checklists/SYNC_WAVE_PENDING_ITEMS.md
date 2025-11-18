# Sync Wave 후속 반영 예정 항목

다른 GPT/리뷰 팀의 점검이 완료되면 아래 항목을 `SYNC_WAVE_VALIDATION.md` 체크리스트에 편입하거나 운영 절차화한다.

## 1. ApplicationSet 템플릿 규칙 ✅
- CI 스크립트 `scripts/ci/lint-appset-templates.sh`와 GitHub Actions `🧹 ApplicationSet Lint` 잡이 literal 따옴표를 강제 차단한다.
- 사용 규칙은 `docs/checklists/SYNC_WAVE_VALIDATION.md` 1번 섹션에 편입됐다.

## 2. Wave 0/10/11 상태 검증 ✅
- `scripts/diagnostics/check-wave-health.sh <env>`로 `*-crds`, `*-external-secrets`, `*-secrets` 애플리케이션을 argocd CLI에서 wait 처리한다.
- 운영 절차는 체크리스트 4번 섹션에 반영됐다.

## 3. Route53 vs ExternalDNS 충돌 방지·보강 ✅
- **조치**:
  1. ExternalDNS Helm overlay(dev/prod `patch-application.yaml`)에 `--annotation-filter=external-dns.alpha.kubernetes.io/managed-by in (external-dns)`를 추가해, 해당 annotation이 있는 리소스만 자동 관리하도록 제한.
  2. 모든 ALB Ingress 패치(`workloads/ingress/*/patch-*.yaml`)에 `external-dns.alpha.kubernetes.io/managed-by: external-dns` annotation과 `growbin.app` 호스트명을 명시해 Route53(Apex)와 ExternalDNS(서브도메인) 책임을 구분.
  3. Cluster documents와 체크리스트에 책임 분리 원칙을 반영.
- **후속**: ExternalDNS가 관리 중인 레코드 목록을 주기적으로 점검하는 스크립트/운영 절차 추가.

## 4. 라벨 프리픽스(`sesacthon.io/`) 표준화 ✅
- **조치 완료**: Argo CD, Kustomize, Helm, Ansible 매니페스트 전반에서 `sesacthon.io/` 라벨/annotation prefix를 `sesacthon.io/`로 일괄 교체해 노드/워크로드 라벨 체계를 통일했다.
- **추가 액션**:
  - 체크리스트와 문서에 “노드/워크로드 라벨은 `sesacthon.io/` prefix 사용” 규칙을 명시.
  - 환경별 라벨 매칭을 `argocd app diff` 등으로 주기적으로 검증하는 절차를 운영 프로세스에 포함.

