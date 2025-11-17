# ExternalDNS 연동 및 동작 흐름

## 1. 구성 개요
- **도메인 구조**
  - 퍼블릭 FQDN: `growbin.app`
  - 환경별 서브도메인: `api.dev.growbin.app`, `grafana.growbin.app`, `argocd.growbin.app` 등
  - Apex 및 핵심 Alias 레코드는 Terraform/Ansible(Route53)에서 관리
  - 서브도메인(Ingress 기반)은 ExternalDNS가 자동 관리
- **ExternalDNS 설정**
  - Helm values(`platform/helm/external-dns/values/{env}.yaml`)에서
    - `domainFilters: [growbin.app]`
    - `txtOwnerId: sesacthon-{env}`
    - `extraArgs`에 `--annotation-filter=external-dns.alpha.sesacthon.io/managed-by in (external-dns)`
  - AWS provider: Route53 public zone

## 2. 동작 흐름
1. **Ingress/Service 정의**
   - `workloads/ingress/apps/**/patch-*.yaml` 등에서 서비스별 Ingress를 선언
   - 각 리소스에 `external-dns.alpha.sesacthon.io/managed-by: external-dns` annotation과 `spec.rules[].host`(예: `api.dev.growbin.app`)를 설정
2. **ExternalDNS 감지**
   - ExternalDNS Pod가 해당 annotation 및 host를 읽고 Route53에 `A`/`CNAME` 레코드를 생성
   - 동일 레코드에 대해 TXT 레코드(`txtOwnerId`)로 소유권을 기록해 충돌 방지
3. **Route53 레코드 생성**
   - 서브도메인: ExternalDNS가 Alias → ALB DNS 로 자동 연동
   - Apex/핵심 도메인: Terraform/Ansible이 유지하며 ExternalDNS는 관여하지 않음
4. **ALB 라우팅**
   - ALB Ingress Controller가 Host/Path 규칙에 따라 각 네임스페이스 서비스로 트래픽 분기

## 3. 운영 수칙
- **책임 분리**
  - Terraform/Ansible: Apex(`growbin.app`, `www.growbin.app`) 및 공용 Alias 레코드
  - ExternalDNS: `external-dns.alpha.sesacthon.io/managed-by=external-dns`가 붙은 Ingress/Service 서브도메인
- **검증 절차**
  1. Ingress 추가 시 반드시 annotation + host를 설정
  2. `kubectl get ingress -A -o jsonpath='{..metadata.annotations.external-dns\\.alpha\\.sesacthon\\.io/managed-by}'` 명령으로 대상 리소스 확인
  3. Route53 콘솔 또는 CLI 로 생성된 레코드가 예상대로 Alias/Target 되는지 점검
- **문서/체크리스트 반영**
  - `docs/checklists/SYNC_WAVE_VALIDATION.md` 2,5번 섹션에서 ExternalDNS 책임 범위 및 annotation 규칙을 확인
  - 문제가 발견되면 `terraform/route53.tf`와 Helm values를 동시에 검토해 충돌 여부를 파악

## 4. 트러블슈팅 포인트
- **레코드가 생성되지 않을 때**
  - Annotation 누락 여부 확인
  - ExternalDNS 로그에서 `skipping record` 메시지 확인 (`kubectl logs -n platform-system deploy/external-dns`)
- **중복/충돌 레코드**
  - TXT 레코드 소유권이 다르면 ExternalDNS가 업데이트하지 못함 → 기존 레코드 삭제 후 재시도
  - Ansible이 관리하는 레코드에 annotation을 넣지 않도록 주의
- **도메인 변경 시**
  - Terraform `domain_name`, ExternalDNS `domainFilters`, Ingress host를 동시에 업데이트
  - Route53 zone이 달라질 경우 ExternalDNS IAM 권한/Hosted Zone ID를 다시 확인

