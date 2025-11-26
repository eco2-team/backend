# Network Policies (L3/L4 Isolation)

Calico 기반 네임스페이스 간 네트워크 격리 정책.

## 구조

- `base/`:
  - ~~`default-deny-all.yaml`: 모든 네임스페이스에 기본 Ingress 차단~~ *(현재는 적용 대기. tier별 정책 정립 이후 다시 enable 예정.)*
  - `allow-dns.yaml`: CoreDNS egress 허용 (필수)
  - `data-ingress.yaml`: tier=business-logic → postgres/redis 허용 (5432, 6379)
  - `monitoring-ingress.yaml`: 모든 NS → prometheus/grafana 접근 허용

- `overlays/dev/`: base 그대로 사용
- `overlays/prod/`: base 그대로 사용 (필요 시 추가 정책)

## 정책 원칙

1. ~~**Default Deny**: 명시적 허용 외 모든 Ingress 차단~~ → *개발/운영 영향으로 현재 보류 중 (2025-11).*
2. **Tier 기반**: `namespaceSelector.matchLabels.tier` 사용 (정책 정립 후 단계적 적용)
3. **L3/L4만**: IP/Port 수준 제어 (FQDN 격리는 차후 Cilium/Istio로 확장)

## 주의사항

- ALB Controller egress 차단 금지 (ImagePullBackOff 발생)
- kube-system 네임스페이스는 정책 제외

## 참고

- `docs/architecture/networking/NETWORK_ISOLATION_POLICY.md`
- Wave 5에서 Calico 직후 배포됨
