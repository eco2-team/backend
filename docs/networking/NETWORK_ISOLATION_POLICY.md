# Network Isolation Policy

> **목표**: CNCF Kubernetes 가이드라인에 따라 동일 클러스터 내 L3/L4 통신을 NetworkPolicy로 통제하고, FQDN(L7) 기반 격리는 후속 단계로 분리한다.  
> **근거 레퍼런스**  
> - Kubernetes 공식 문서 *“Using Network Policies”* (sesacthon.io/docs/concepts/services-networking/network-policies)  
> - CNCF Cilium / Calico 자료 (FQDN 정책은 CNI 확장 기능)  
> - Istio egress/Envoy L7 정책 가이드

---

## 1. 범위

| 구분 | 설명 | 현재 전략 |
|------|------|-----------|
| 레이어(Tier) 격리 | 네임스페이스·라벨 기반 L3/L4 트래픽 제어 | **즉시 적용** (Sync Wave 5 Network) |

---

## 2. 레이어(L3/L4) 격리

### 원칙
1. **기본 Deny**: 모든 Namespace에 `deny-all` NetworkPolicy를 Wave 5에서 배포해 외부/내부 통신을 명시적으로 허용하도록 강제한다.  
2. **라벨 기반 허용**: Pod/Namespace Selector를 활용해 레이어(Business Logic: API + Worker, Integration: RabbitMQ, Database: Redis, PostgreSQL)을 상호 격리하고 필요한 경우에만 ingress/egress 룰을 추가한다. (Kubernetes NetworkPolicy 자체가 “IP address 또는 port level, 즉 OSI L3/L4” 제어만 제공함을 공식 문서가 명시하고 있기 때문에,[[1]](#ref-k8s-np) 라벨/네임스페이스 기반으로 IP 집합을 정의하는 것이 최선이다.)  
3. **Sync Wave 연계**: NetworkPolicy는 네임스페이스/RBAC 이후, Platform/Ingress 이전(Wave 5) 배포로 지정한다. (`ARGOCD_SYNC_WAVE_PLAN.md` 반영)

### 표준 템플릿 (Calico)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-namespace-dns
  namespace: api-auth
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              sesacthon.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
```

> Kubernetes 공식 스펙은 IP/포트 기준이므로 DNS 서비스(ClusterIP)로 허용한 뒤 외부 CIDR을 별도로 열어야 한다.

---

## 3. 도메인(FQDN) 격리 (L2 격리)

### 제약
- K8s NetworkPolicy는 FQDN 매칭을 지원하지 않으며, IP/포트(L3/L4) 수준의 흐름만 제어한다.[[1]](#ref-k8s-np)  
- Calico Open Source 역시 같은 제약을 가지며, Tigera의 공식 기능 비교표에서도 “DNS/FQDN-based policy” 항목은 Calico Cloud/Enterprise 에디션에서만 제공된다.[[2]](#ref-calico-matrix)  
- IP/CIDR 변동이 잦은 SaaS/FQDN을 NetworkPolicy로 관리하면 유지보수가 불가능.

### 옵션 비교

| 접근 | 장점 | 단점 |
|------|------|------|
| **Cilium FQDNPolicy** | DNS 기반 L7 필터링, eBPF 고성능 | Cilium CNI 도입 필요, 운영 복잡 |
| **Calico Enterprise / Cloud** | Managed UI/Policy, FQDN 지원 | 상용 요금제 |
| **GKE/AKS FQDN NetworkPolicy** | Managed CNI에서 네이티브 지원 | 특정 클라우드에 종속 |
| **Istio/Envoy egress gateway** | L7 HTTP/TLS 인식, 세밀한 정책 | Service Mesh 도입 필요, 오버헤드 |

### 로드맵
1. Worker/Infra 네임스페이스에 Istio Sidecar 주입 검토 (Wave 30+).  
2. Cilium adoption PoC로 FQDN 기반 통제 가능성 평가.  
3. 정책/보안팀과 도메인 allowlist 기준 수립 이후 Sync Wave 반영.

---

## 4. Sync Wave 정책

| Wave | 작업 | 내용 |
|------|------|------|
| Wave -1 | Namespaces | 레이블 표준화 (`tier`, `role`, `app.sesacthon.io/*`) |
| Wave 0 | RBAC/Storage | NetworkPolicy에서 참조할 ServiceAccount/클래스 준비 |
| **Wave 5** | **Network** | default-deny, DNS 허용, 동일 Layer 허용 정책 배포 |
| Wave 10+ | Platform/Ingress | 레이어 격리 성공 시 TLS/Ingress 배포 |
| Wave 60+ | Apps | Layer 정책 준수 확인 후 애플리케이션 배포 |

---

## 5. 운영 절차

1. **템플릿 관리**: `k8s/networkpolicies/base`에서 공통 정책을 관리하고, Namespace Overlay로 허용 룰을 확장한다.  
2. **검증**: `kubectl exec` + `nc`/`wget` 테스트, Calico `calicoctl endpoint show` 등으로 적용 결과를 점검.  
3. **감사**: NetworkPolicy 변경 시 GitOps PR 템플릿에 영향 분석(허용 대상, 포트)을 기재한다.  
4. **예외 처리**: 임시로 허용해야 할 경우 `temporary-egress-<ticket>` 정책을 만들고 만료일/삭제 책임자를 주석으로 명시한다.

---

## 5. 요약
- **지금**: L3/L4 레벨 격리를 NetworkPolicy로 완비하고, Sync Wave 5에서 자동 배포.  
- **문서 연계**: `ARGOCD_SYNC_WAVE_PLAN.md`, `NAMESPACE_NETWORKPOLICY_INGRESS.md`와 일관성을 유지하며 업데이트한다.

---

## 참고
1. <a name="ref-k8s-np"></a>[Kubernetes NetworkPolicy](https://sesacthon.io/docs/concepts/services-networking/network-policies/) 공식 문서

