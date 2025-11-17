# 네임스페이스 · 네트워크 정책 · 인그레스 설계

> 작성일: 2025-11-16  
> 담당 범위: Kustomize Wave 00/01, NetworkPolicy, ALB Ingress

---

## 1. 네임스페이스 계층 구조

| Tier | Namespace | 용도 | Wave | 소스 |
|------|-----------|------|------|------|
| Business Logic | `auth`, `my`, `scan`, `character`, `location`, `info`, `chat` | API 계층 | 00 | `workloads/namespaces/base/namespaces.yaml` |
| Data | `postgres`, `redis` | Database · Cache | 00 | ↑ |
| Integration | `rabbitmq` | 메시지 브로커 | 00 | ↑ |
| Observability | `prometheus`, `grafana` | 모니터링 스택 | 00 | ↑ |
| Infrastructure | `platform-system`, `data-system`, `messaging-system` | Operators | 00 | ↑ |

- **배포 파이프라인**: `argocd/apps/00-namespaces.yaml` → `k8s/namespaces/kustomization.yaml`  
- **레이블 표준**: `name`, `domain`, `tier`, `role`, `app.kubernetes.io/*`
- **운영 원칙**: 네임스페이스는 GitOps 단일 소스에서만 생성/수정하며, Ansible이나 수동 `kubectl` 적용을 금지한다.

---

## 2. 네트워크 정책 설계

### 2.1 Tier 격리 정책

- **적용 Wave**: 05 (ArgoCD `06-network-policies.yaml`)  
- **핵심 규칙**
  - `tier=business-logic` → `tier=data` 대상만 TCP 5432/6379 허용
  - `tier=integration`(rabbitmq) ingress는 business-logic 네임스페이스만 허용
  - `tier=observability` 중 `prometheus`는 모든 네임스페이스로부터 9090/8080을 수집, `grafana`는 ALB에서 3000만 허용

### 2.2 ALB Controller 전용 정책

- **허용 대상**
  - IMDS: `169.254.169.254/32` (IRSA 미사용 시 자격증명 조회)
  - Kubernetes API: `10.96.0.1/32` 및 `kube-system` DNS (TCP/UDP 53)
  - Control-plane subnet: `10.0.0.0/8`
  - AWS API: `0.0.0.0/0` TCP 443 (ELB/EC2/STS)

> 📝 **운영 메모**  
> ALB Controller(`kube-system`)는 Kubernetes API, DNS, AWS API, IMDS로 egress 할 수 있어야 한다. Wave 05 NetworkPolicy 배포 시 ALB Controller 전용 egress 정책을 함께 적용한다.

---

## 3. 인그레스 설계

### 3.1 도메인 기반 ALB 인그레스

- **특징**
  - 모든 API가 **단일 ALB 그룹(`alb.ingress.kubernetes.io/group.name: ecoeco-main`)**을 공유
  - Listener: HTTPS 443 단일 포트, 백엔드는 HTTP(NodePort)로 통일
  - ACM 인증서 ARN은 Terraform output(`acm_certificate_arn`)에서 주입
  - 헬스체크 `/health`, 인터벌 30s, 타임아웃 5s
  - 각 도메인별 `path: /api/v1/<domain>` Prefix 매칭

### 3.2 인프라 인그레스

- **대상 서비스**
  - ArgoCD (`argocd.growbin.app`)
  - Atlantis (`atlantis.growbin.app`)
  - Grafana/Prometheus 등 Ops 포털
- **주요 차이점**
  - 별도의 ALB 그룹/우선순위 사용 (예: `alb.ingress.kubernetes.io/group.order: 5`)
  - 일부 서비스는 IP 화이트리스트/Basic Auth를 주석으로 안내

---

## 4. 트러블슈팅: ALB Controller Egress 오설정

| 구분 | 내용 |
|------|------|
| 증상 | `aws-load-balancer-controller` 파드가 `CrashLoopBackOff`, 로그: `unable to create controller ... dial tcp 10.96.0.1:443: i/o timeout` |
| 근본 원인 | ALB Controller 전용 egress 정책이 누락되거나 `namespaceSelector: {}` + TCP 80/443만 허용하도록 잘못 배포되어 Kubernetes API(ClusterIP 10.96.0.1)로 나가는 트래픽이 차단됨 |
| 영향 | ALB Controller MutatingWebhook(포트 443) 호출 실패 → 모든 Service/Ingress Sync가 실패, Helm 설치 및 ArgoCD Wave 40/60가 연쇄 OutOfSync |
| 해결 | 1) `alb-controller-egress` 정책을 API/DNS/IMDS/AWS API별로 명시한 버전으로 교체, 2) Wave 01(Infrastructure) Kustomize에 포함, 3) `kubectl rollout restart deployment/aws-load-balancer-controller -n kube-system` |
| 사후 조치 | - 네임스페이스/정책 파일을 단일 GitOps 경로에서 관리<br>- ALB Controller 관련 NetworkPolicy 변경 시 반드시 `kubectl logs`와 `kubectl describe networkpolicy`로 검증 프로세스 추가 |

### 4.1 권장 ingress/egress 체크리스트

1. **Ingress**
   - ACM ARN 유효성 (`terraform output acm_certificate_arn`)
   - `alb.ingress.kubernetes.io/group.order` 중복 여부
   - Healthcheck path가 실제 API에 존재하는지 확인
2. **Egress**
   - Kubernetes API CIDR (`10.96.0.1/32`) 허용 여부
   - DNS(`kube-system`, TCP/UDP 53) 허용 여부
   - AWS API(0.0.0.0/0:443) 허용 여부
   - IMDS(169.254.169.254/32) 접근 필요 여부 판단

---

## 5. 향후 작업 가이드

1. **Wave 재정의**
   - Wave 00: `k8s/namespaces`
   - Wave 01: `k8s/networkpolicies`
   - Wave 10+: Helm/Kustomize 모듈(Platform, Monitoring, Data)
2. **Helm/Kustomize 통합 리팩터링**
   - Namespace/Policy/Ingress 정의를 본 문서대로 재구성 후, 설계 문서와 코드가 항상 1:1 매핑되도록 유지
3. **문서 연계**
   - 본 문서는 `docs/architecture/networking`의 기준 문서로 사용
   - Troubleshooting 사례는 `docs/TROUBLESHOOTING.md` 19장과 링크 예정

---

> 이 문서는 네임스페이스 격리부터 ALB 인그레스까지 GitOps 기반으로 재설계하기 위한 표준 참고자료다. 이후 Helm Chart 구조 리팩터링 시 본 문서의 계층/의존성을 기준으로 삼는다.


