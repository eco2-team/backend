# Eco² Istio Service Mesh Migration Plan

## 1. Introduction

### 1.1 Background
현재 Eco² 클러스터는 **AWS ALB + K8s Ingress** 기반의 North-South 트래픽 처리와, **Calico CNI** 기반의 East-West 트래픽 제어를 수행하고 있습니다. 그러나 MSA 구조가 고도화됨에 따라 다음과 같은 한계점이 식별되었습니다.

*   **강한 인증 의존성:** 각 마이크로서비스(`scan-api`, `chat-api` 등)가 코드 레벨에서 JWT 검증 및 Cookie 파싱을 직접 수행하고 있어, 비즈니스 로직의 순수성이 저해되고 있습니다.
*   **L7 트래픽 제어의 부재:** 특정 헤더 기반 라우팅이나 정교한 트래픽 제어(Canary, Circuit Breaker)를 구현하기 어렵습니다.
*   **가시성(Observability) 파편화:** 서비스 간 호출 관계나 지연 시간(Latency) 분석이 애플리케이션 로그에 의존하고 있어 전체적인 토폴로지 파악이 어렵습니다.

### 1.2 Objectives
**Istio Service Mesh**를 도입하여 다음 목표를 달성하고자 합니다.

1.  **Authentication Offloading:** 인증 로직(JWT 검증)을 애플리케이션에서 **Istio Sidecar(Envoy)**로 위임하여 **Zero-Trust Security**를 구현하고 개발 생산성을 높입니다.
2.  **Advanced Traffic Management:** **Istio Ingress Gateway**를 통해 Cookie-to-Header 변환 등 복잡한 라우팅 로직을 인프라 레벨에서 처리합니다.
3.  **Enhanced Observability:** 코드 수정 없이 서비스 간 통신 메트릭, 로그, 트레이싱 정보를 자동으로 수집합니다.

---

## 2. Architecture Changes

### 2.1 Traffic Flow (North-South)

| 구분 | AS-IS (Current) | TO-BE (With Istio) |
| :--- | :--- | :--- |
| **Entry Point** | AWS ALB | AWS NLB (or ALB) |
| **Ingress Controller** | AWS Load Balancer Controller | **Istio Ingress Gateway** |
| **Resource** | `Ingress` (K8s Native) | `Gateway` + `VirtualService` (Istio CRD) |
| **Routing Logic** | Path-based (ALB Rule) | **L7 Routing** (Header, Cookie, Path, etc.) |

*   **변경점:** 기존 `Ingress` 리소스 대신 Istio의 `Gateway`와 `VirtualService`를 사용하여 라우팅을 정의합니다. AWS ALB Controller는 Istio Ingress Gateway Service(`LoadBalancer` 타입)를 노출하는 역할로 축소되거나 NLB로 대체될 수 있습니다.

### 2.2 Authentication Flow

| 구분 | AS-IS (Code Level) | TO-BE (Mesh Level) |
| :--- | :--- | :--- |
| **Token Extraction** | Python Code (`Cookie` 파싱) | **EnvoyFilter** (Cookie → Header 변환) |
| **Token Validation** | Python Code (`jwt.decode`) | **RequestAuthentication** (Envoy가 검증) |
| **Authorization** | Python Code (`if user.role...`) | **AuthorizationPolicy** (Role 기반 접근 제어) |
| **App Responsibility** | 인증/인가 + 비즈니스 | **비즈니스 로직 Only** |

---

## 3. Migration Roadmap

### Phase 1: Istio Installation (Base & Control Plane) - ✅ Completed
가장 먼저 Istio의 기반이 되는 CRD와 Control Plane(`istiod`)을 설치합니다. 기존 애플리케이션에 영향을 주지 않습니다.

*   **Sync Wave 4:** `istio-base`, `istiod`
*   **Target Node:** `k8s-master` (Resource 여유분 활용)
*   **Profile:** `default` (프로덕션 권장)

### Phase 2: Ingress Gateway & Routing Setup - ✅ Completed
Traffic의 입구가 될 Ingress Gateway와 라우팅 규칙(`VirtualService`)을 설정합니다. `workloads/ingress` 폴더를 `workloads/routing`으로 리팩토링하여 관리합니다.

*   **Sync Wave 5:** `istio-ingressgateway` (NodePort Type for ALB Controller)
*   **Sync Wave 50:** `VirtualService`, `Gateway` (Application 배포 전 라우팅 준비)
*   **Service Type Migration:** 기존 도메인(`auth`, `scan` 등)의 Service 타입을 `NodePort`에서 **`ClusterIP`**로 변경하여 클러스터 내부 보안을 강화합니다.

### Phase 3: Cookie to Header Strategy (Bridge) - ✅ Completed
프론트엔드 수정 없이 백엔드 인증 구조를 개선하기 위해, Istio Ingress Gateway에서 **`EnvoyFilter`**를 사용하여 `Cookie`를 `Authorization Header`로 변환합니다.

1.  **EnvoyFilter:** `s_access` 쿠키 추출 → `Authorization: Bearer <token>` 헤더 주입.
2.  **Backend:** `Cookie` 의존성 제거, `Authorization` 헤더 기반 검증 로직으로 단일화.

### Phase 4: Sidecar Injection (Full Mesh) - ✅ Completed
모든 서비스에 Sidecar를 주입하여 mTLS 및 Observability를 확보합니다.

1.  `istio-injection=enabled` 라벨 적용 (Namespace 단위)
2.  `Deployment` 재시작 → `istio-proxy` 컨테이너 주입
3.  **Health Check:** `Readiness Probe`가 정상 동작하는지 확인 (mTLS 이슈 주의)

### Phase 5: Auth Offloading (Final Goal) - ✅ Completed
트래픽이 안정화되면, 애플리케이션의 인증 로직을 제거하고 Istio 정책으로 대체합니다.

1.  **RSA Key Migration:** JWT 서명 알고리즘을 `HS256`에서 `RS256`으로 전환하고 JWKS 엔드포인트 구현.
2.  **RequestAuthentication:** Istio Gateway에서 JWT 서명 검증 수행.
3.  **Code Refactoring:** 애플리케이션(`dependencies.py`)에서 검증 로직 제거, 헤더 파싱만 수행하도록 경량화.

### Phase 6: Advanced AuthZ & Observability (Next Step)
보안 및 관측성을 더욱 강화하기 위해 다음 단계를 진행합니다.

1.  **External Authorization (gRPC):**
    *   `auth-api`에 gRPC 서버를 내장하여 Istio의 `CUSTOM` Authorization 요청을 처리.
    *   Redis Blacklist 체크 로직을 인프라 레벨(Istio -> Auth gRPC)로 이관하여 애플리케이션 로직 완전 분리.
2.  **Observability Offloading:**
    *   `metrics.py` 미들웨어 제거. (`http_requests_total` 등 표준 메트릭은 Envoy가 자동 수집)
    *   Access Log 포맷을 JSON으로 변경하여 ELK Stack 등으로의 수집 효율화.
    *   비즈니스 로직에 특화된 커스텀 메트릭(예: AI Pipeline Step Latency)만 코드에 남김.

---

## 4. Implementation Details (Hands-on Guide)

### 4.1 Helm Chart Configuration (ArgoCD)
우리는 ArgoCD App-of-Apps 패턴을 사용하므로, `clusters/dev/apps/05-istio.yaml`에 다음과 같이 정의합니다.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dev-istiod
  annotations:
    argocd.argoproj.io/sync-wave: "4"
spec:
  source:
    chart: istiod
    repoURL: https://istio-release.storage.googleapis.com/charts/
    targetRevision: 1.24.1
    helm:
      valuesObject:
        pilot:
          nodeSelector:
            role: control-plane
          tolerations:
          - key: role
            operator: Equal
            value: control-plane
            effect: NoSchedule
```

### 4.2 Cookie to Header Conversion (Lua Filter)
앱이 Cookie 인증을 Header 인증으로 전환하기 전까지 과도기적으로 사용할 EnvoyFilter입니다.

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: cookie-to-header
spec:
  workloadSelector:
    labels:
      istio: ingressgateway
  configPatches:
  - applyTo: HTTP_FILTER
    match:
      context: GATEWAY
    patch:
      operation: INSERT_BEFORE
      value:
        name: envoy.lua
        typed_config:
          "@type": "type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua"
          inlineCode: |
            function envoy_on_request(request_handle)
              local cookie_header = request_handle:headers():get("cookie")
              if cookie_header then
                local token = string.match(cookie_header, "s_access=([^;]+)")
                if token then
                  request_handle:headers():add("Authorization", "Bearer " .. token)
                end
              end
            end
```

### 4.3 Gateway Node Provisioning (Terraform & Ansible)
기존 클러스터 영향 없이 **Istio Ingress Gateway 전용 노드**를 추가하고 클러스터에 조인시키는 절차입니다.

**1. Terraform Apply (Node Creation)**
```bash
cd terraform
# 변경 사항 확인 (ingress_gateway 모듈 추가 확인)
terraform plan -var-file=env/dev.tfvars
# 적용
terraform apply -var-file=env/dev.tfvars
```

**2. Ansible Provisioning (Node Join)**
```bash
cd ansible
# 새로 생성된 ingress_gateway 그룹만 타겟팅하여 K8s Join 실행
ansible-playbook -i inventory/hosts.ini playbooks/03-worker-join.yml --limit ingress_gateway
```

**3. Verification**
```bash
kubectl get nodes -l role=ingress-gateway
# STATUS: Ready 확인
```

---

## 5. Rollback Plan

만약 마이그레이션 중 심각한 장애(Latency 급증, 5xx 에러 등)가 발생할 경우 다음과 같이 롤백합니다.

1.  **Traffic Rollback:** DNS 레코드 또는 ALB 타겟 그룹을 다시 기존 `Ingress Controller`로 원복합니다.
2.  **Sidecar Removal:** Namespace의 `istio-injection` 라벨을 제거하고 `rollout restart`를 수행하여 Sidecar를 제거합니다.
3.  **Uninstall:** 최악의 경우 ArgoCD에서 Istio 앱을 삭제합니다. (CRD 잔존 주의)

---

## 6. References
*   [Istio Official Docs: Installation with Helm](https://istio.io/latest/docs/setup/install/helm/)
*   [Istio Security: Authentication Policies](https://istio.io/latest/docs/tasks/security/authentication/authn-policy/)
*   [EnvoyFilter Examples](https://istio.io/latest/docs/reference/config/networking/envoy-filter/)
*   [Cookie Based Routing in Istio](https://istio.io/latest/docs/tasks/traffic-management/request-routing/#route-based-on-user-identity)
