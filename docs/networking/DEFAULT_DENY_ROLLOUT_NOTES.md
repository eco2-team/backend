# Default Deny NetworkPolicy 롤아웃 메모 (2025-11-17)

> 목적: `workloads/network-policies`의 default deny 전략을 일시 중단한 배경과, 향후 재적용 시 필수 고려사항을 정리한다. ArgoCD 기반 GitOps에서 언제든지 안전하게 되돌릴 수 있는 체크리스트 역할을 한다.

---

## 1. 현재 상태
- `workloads/network-policies/base/kustomization.yaml`에서 `default-deny-all.yaml`을 제외했다. (`commit: TBD`)
- `default-deny-all.yaml` 자체는 파일로 남겨두고 상단 주석에 “추후 재활성화 시 kustomization에 다시 포함” 지침을 추가했다.
- 적용 중인 정책은 `allow-dns.yaml`, `data-ingress.yaml`, `monitoring-ingress.yaml`뿐이며, tier별 라벨 정책은 아직 정의되지 않았다.
- ArgoCD `dev-network-policies` Application은 오류 없이 Sync 가능하다. (default deny 제거로 인해 리소스 삭제 없이 정책 업데이트만 발생)

---

## 2. 일시 중단 사유
1. **서비스 가용성**: tier별 허용 규칙이 없는 상태에서 default deny를 적용하면 API 네임스페이스가 모두 차단되어 ALB TargetGroup 헬스체크가 전부 실패한다.
2. **운영 파급**: GitOps Sync Wave 6(네트워크) 직후 Wave 15+ (ALB, ExternalDNS, 모니터링 등)까지 연쇄 OutOfSync 사례가 재발할 수 있다.
3. **ArgoCD/Webhook 영향**: `argocd` 네임스페이스에도 default deny가 적용되면 Git webhook, repo-server, notifications 등의 Ingress/Egress를 다시 정의해야 하므로 장기간 공백이 생긴다.

---

## 3. 재적용 전 체크리스트
| 구분 | 항목 | 설명 |
|------|------|------|
| 정책 준비 | Tier 라벨 표준 | `tier=business-logic`, `tier=data`, `tier=observability`, `tier=integration` 라벨이 모든 네임스페이스/Pod에 적용되었는지 확인 |
| 예외 설계 | 서비스 허용 정책 | ALB/Ingress → API 네임스페이스, 내부 gRPC, CronJob 등 필요한 Ingress 룰을 사전에 명시 |
| 인프라 보호 | `kube-system` egress | `aws-load-balancer-controller`, ExternalDNS, Metrics Server 등 필수 Pod에 대한 egress 허용 정책 작성 (API 10.96.0.1/32, DNS 53, AWS API 443, IMDS 169.254.169.254/32) |
| GitOps 정합성 | Kustomize diff | `kustomize build workloads/network-policies/dev`로 default deny가 추가되었을 때 생성 리소스를 미리 검증 |
| 단계적 배포 | Sync Wave | dev → staging → prod 순으로 Wave 6 Application Sync, 각 단계마다 `kubectl exec ... nc`로 실제 통신 허용 여부 테스트 |

---

## 4. 롤백/재활성화 절차
1. `workloads/network-policies/base/kustomization.yaml`에 `default-deny-all.yaml`을 다시 추가한다.
2. 필요하면 네임스페이스별로 default deny를 분리(예: `auth-default-deny.yaml`)해 서비스 그룹 단위로 점진적 적용이 가능하도록 한다.
3. `docs/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md`의 체크리스트(2.2, 4장)를 최신 상태로 맞춘다.
4. ArgoCD `dev-network-policies` Application을 Sync하고, 영향 있는 네임스페이스에서 `kubectl describe networkpolicy`로 최종 룰을 확인한다.

---

## 5. 테스트 가이드
```bash
# 1. DNS 허용 확인
kubectl -n auth exec deploy/auth-api -- nslookup kubernetes.default

# 2. DB 통신 확인
kubectl -n auth exec deploy/auth-api -- nc -vz postgres.postgres.svc.cluster.local 5432

# 3. Prometheus/Grafana 수집 경로 확인
kubectl -n prometheus exec deploy/prometheus -- nc -vz auth-api.auth.svc.cluster.local 8000
```

> 모든 테스트가 통과한 뒤에만 default deny를 다시 enable 한다. 실패 시 `kubectl get events -n <ns>`와 `calicoctl`을 활용해 차단 구간을 식별한다.

---

## 6. 후속 과제
1. Tier별 Ingress/Egress 매트릭스 문서화 (`docs/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md` 연동)
2. NetworkPolicy CI 검사(Job) 작성: `kubectl apply --dry-run=server`, `netpol lint` 등
3. ArgoCD App-of-Apps 파이프라인에 “네트워크 정책 승인” 체크 단계를 추가해 무분별한 default deny enable을 방지

---

**마지막 업데이트**: 2025-11-17  
**담당자**: Platform Networking Team

