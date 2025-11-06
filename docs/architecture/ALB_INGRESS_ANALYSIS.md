# ALB + Ingress 구성 분석 및 개선 방안

> 참고: [Kubernetes NodePort vs LoadBalancer vs Ingress](https://12bme.tistory.com/830)  
> 날짜: 2025-11-04  
> 현재 구성: AWS ALB + Kubernetes Ingress (Path-based Routing)

---

## 📋 참고 글 요약

### Kubernetes 외부 노출 방법 비교

| 방식 | 용도 | 장점 | 단점 |
|------|------|------|------|
| **ClusterIP** | 클러스터 내부 통신 | 기본 서비스, 안전 | 외부 접근 불가 |
| **NodePort** | 개발/테스트 | 간단, 빠름 | 포트 제한(30000-32767), 관리 어려움 |
| **LoadBalancer** | 단일 서비스 노출 | 직접 노출, 모든 프로토콜 지원 | 서비스당 LB 필요, 비용 증가 |
| **Ingress** | 다수 서비스 노출 | 단일 LB로 여러 서비스, L7 라우팅, 비용 효율 | 설정 복잡, HTTP/HTTPS만 지원 |

### Ingress의 핵심 특징
- **스마트 라우터**: 여러 서비스 앞에 위치
- **경로 기반 라우팅**: `/api`, `/grafana`, `/argocd` 등
- **서브도메인 기반 라우팅**: `api.domain.com`, `grafana.domain.com`
- **SSL/TLS 자동화**: cert-manager 통합
- **비용 효율**: 단일 LoadBalancer로 다수 서비스 처리

---

## 🔍 현재 구성 분석

### 1️⃣ 현재 아키텍처

```
Internet
   ↓
AWS ALB (L7 HTTP/HTTPS)
   ↓ (target-type: instance)
NodePort (30000-32767)
   ↓
ClusterIP Service
   ↓
Pod (Calico Overlay Network: 192.168.0.0/16)
```

**구성 요소**:
- **AWS Load Balancer Controller** (Helm 배포)
- **Ingress Resources** (3개): argocd-ingress, grafana-ingress, api-ingress
- **ALB Group**: `growbin-alb` (단일 ALB로 모든 Ingress 통합)
- **SSL/TLS**: ACM Certificate (Terraform 관리)
- **Routing**: Path-based (`/argocd`, `/grafana`, `/api/v1`)

### 2️⃣ 현재 Ingress 설정

#### ArgoCD Ingress
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
  namespace: argocd
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance  # ✅ Calico 호환
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'  # ✅ HTTP → HTTPS
    alb.ingress.kubernetes.io/certificate-arn: <ACM_ARN>
    alb.ingress.kubernetes.io/group.name: growbin-alb  # ✅ 단일 ALB
    alb.ingress.kubernetes.io/group.order: '10'
    alb.ingress.kubernetes.io/backend-protocol: HTTPS  # ArgoCD는 HTTPS
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /argocd
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
```

#### Grafana Ingress
```yaml
metadata:
  name: grafana-ingress
  namespace: monitoring
  annotations:
    alb.ingress.kubernetes.io/group.order: '20'
    # backend-protocol: HTTP (Grafana는 HTTP)
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /grafana
        pathType: Prefix
        backend:
          service:
            name: prometheus-grafana
            port:
              number: 80
```

#### API Ingress
```yaml
metadata:
  name: api-ingress
  namespace: default
  annotations:
    alb.ingress.kubernetes.io/group.order: '30'
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /api/v1
        pathType: Prefix
        backend:
          service:
            name: default-backend  # 향후 실제 API 서비스로 교체
            port:
              number: 80
      - path: /
        pathType: Prefix
        backend:
          service:
            name: default-backend
            port:
              number: 80
```

---

## ✅ 참고 글과의 비교

### 🎯 일치하는 부분 (모범 사례)

| 항목 | 참고 글 권장사항 | 현재 구성 | 상태 |
|------|----------------|----------|------|
| **단일 ALB 사용** | 비용 효율화 | `alb.ingress.kubernetes.io/group.name: growbin-alb` | ✅ |
| **Path-based Routing** | `/api`, `/admin` 등 | `/argocd`, `/grafana`, `/api/v1` | ✅ |
| **SSL/TLS** | cert-manager 권장 | ACM Certificate (AWS 네이티브) | ✅ |
| **HTTP → HTTPS Redirect** | 보안 강화 | `ssl-redirect: '443'` | ✅ |
| **Ingress Controller** | 다양한 선택지 | AWS Load Balancer Controller | ✅ |
| **L7 라우팅** | HTTP/HTTPS만 지원 | HTTP/HTTPS | ✅ |

### ⚠️ 개선 가능한 부분

#### 1️⃣ 서브도메인 기반 라우팅 미구현
**참고 글**:
```yaml
rules:
- host: foo.mydomain.com  # 서브도메인
  http:
    paths:
    - backend:
        serviceName: foo
        servicePort: 8080
- host: mydomain.com
  http:
    paths:
    - path: /bar/*  # 경로 기반
      backend:
        serviceName: bar
        servicePort: 8080
```

**현재**: Path-based만 사용 (`growbin.app/argocd`, `growbin.app/grafana`)

**개선안**: 서브도메인 추가 지원
- `argocd.growbin.app` → ArgoCD
- `grafana.growbin.app` → Grafana
- `api.growbin.app` → API Services
- `growbin.app` → Frontend (Root)

**장점**:
- ✅ URL이 더 깔끔 (`/argocd` prefix 불필요)
- ✅ CORS 설정 간소화
- ✅ 서비스별 독립적인 인증/보안 정책 적용 가능

**단점**:
- ⚠️ Route53 레코드 추가 필요 (서브도메인당 1개)
- ⚠️ ACM 인증서에 와일드카드(`*.growbin.app`) 필요

---

#### 2️⃣ Health Check 커스터마이징 부족
**현재**: ALB 기본 Health Check 사용

**개선안**:
```yaml
annotations:
  alb.ingress.kubernetes.io/healthcheck-path: /argocd/health  # Path prefix와 일치
  alb.ingress.kubernetes.io/healthcheck-protocol: HTTP
  alb.ingress.kubernetes.io/healthcheck-port: traffic-port
  alb.ingress.kubernetes.io/healthcheck-interval-seconds: '15'
  alb.ingress.kubernetes.io/healthcheck-timeout-seconds: '5'
  alb.ingress.kubernetes.io/healthy-threshold-count: '2'
  alb.ingress.kubernetes.io/unhealthy-threshold-count: '2'
  alb.ingress.kubernetes.io/success-codes: '200,404'
```

**장점**:
- ✅ 빠른 장애 감지
- ✅ 트래픽 분산 최적화
- ✅ 서비스별 Health Check 엔드포인트 지정 (path prefix 포함)

---

#### 3️⃣ WAF 통합 고려
**참고 글**: Ingress가 WAF, Shield 통합 가능

**현재**: WAF 미사용 (`enableWaf=false`)

**개선안** (프로덕션):
```yaml
annotations:
  alb.ingress.kubernetes.io/wafv2-acl-arn: <WAF_ACL_ARN>
  alb.ingress.kubernetes.io/shield-advanced-protection: 'true'
```

**장점**:
- ✅ DDoS 방어 (AWS Shield)
- ✅ SQL Injection, XSS 차단 (AWS WAF)
- ✅ Rate Limiting

**우선순위**: 중 (프로덕션 배포 전)

---

#### 4️⃣ Ingress Class 사용 (deprecated 경고)
**현재**:
```yaml
annotations:
  kubernetes.io/ingress.class: alb  # ⚠️ Deprecated (v1.22+)
```

**개선안** (최신 방식):
```yaml
apiVersion: networking.k8s.io/v1
kind: IngressClass
metadata:
  name: alb
spec:
  controller: ingress.k8s.aws/alb
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: argocd-ingress
spec:
  ingressClassName: alb  # ✅ 권장 방식
  rules:
  - host: growbin.app
    ...
```

**장점**:
- ✅ Kubernetes v1.22+ 표준 준수
- ✅ 명시적인 Ingress Controller 지정
- ✅ 여러 Ingress Controller 혼용 가능

---

#### 5️⃣ 백엔드 프로토콜 명시 부족
**현재**:
- ArgoCD: `backend-protocol: HTTPS` ✅
- Grafana: 명시 없음 (기본값: HTTP) ✅
- API: 명시 없음 ❌

**개선안**:
```yaml
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP  # 명시적 선언
  alb.ingress.kubernetes.io/backend-protocol-version: HTTP1  # or HTTP2
```

---

#### 6️⃣ Target Group Attributes 최적화
**현재**: 기본값 사용

**개선안**:
```yaml
annotations:
  alb.ingress.kubernetes.io/target-group-attributes: |
    deregistration_delay.timeout_seconds=30,
    stickiness.enabled=true,
    stickiness.lb_cookie.duration_seconds=86400,
    load_balancing.algorithm.type=least_outstanding_requests
```

**효과**:
- ✅ 빠른 스케일 다운 (deregistration_delay 감소)
- ✅ 세션 유지 (stickiness)
- ✅ 효율적인 부하 분산 (least_outstanding_requests)

---

## 🎯 권장 개선 사항 우선순위

### 🔥 높음 (즉시 적용 권장)

#### 1. IngressClass 마이그레이션
**현재 문제**: `kubernetes.io/ingress.class` annotation 사용 (deprecated)

**해결책**: `IngressClass` 리소스 생성 및 `ingressClassName` 필드 사용

**파일**: `ansible/playbooks/07-1-ingress-class.yml` (신규)
```yaml
---
- name: "IngressClass 생성 (alb)"
  shell: |
    kubectl apply -f - <<EOF
    apiVersion: networking.k8s.io/v1
    kind: IngressClass
    metadata:
      name: alb
      annotations:
        ingressclass.kubernetes.io/is-default-class: "true"
    spec:
      controller: ingress.k8s.aws/alb
    EOF
  register: ingress_class

- name: "IngressClass 확인"
  command: kubectl get ingressclass
  register: ic_list
  changed_when: false

- name: "IngressClass 정보 출력"
  debug:
    msg: "{{ ic_list.stdout_lines }}"
```

**Ingress 수정**: `07-ingress-resources.yml`
```yaml
# Before
metadata:
  annotations:
    kubernetes.io/ingress.class: alb  # ❌ Deprecated

# After
spec:
  ingressClassName: alb  # ✅ 권장
```

---

#### 2. Health Check 커스터마이징
**파일**: `07-ingress-resources.yml` 수정

```yaml
annotations:
  # 기존 annotations...
  alb.ingress.kubernetes.io/healthcheck-path: /argocd/health  # Path prefix와 일치
  alb.ingress.kubernetes.io/healthcheck-interval-seconds: '15'
  alb.ingress.kubernetes.io/healthcheck-timeout-seconds: '5'
  alb.ingress.kubernetes.io/healthy-threshold-count: '2'
  alb.ingress.kubernetes.io/unhealthy-threshold-count: '2'
```

**추가 작업**:
- ArgoCD: `/argocd/health` 엔드포인트 (path prefix 포함)
- Grafana: `/grafana/health` 엔드포인트 (path prefix 포함)
- API Services: `/api/health` 엔드포인트 구현 필요

---

### ⚠️ 중간 (향후 개선)

#### 3. 서브도메인 기반 라우팅 추가
**전제 조건**:
1. ACM 인증서에 와일드카드 추가 (`*.growbin.app`)
2. Route53에 서브도메인 레코드 추가

**Terraform 수정**: `terraform/acm.tf`
```hcl
resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = [
    "*.${var.domain_name}",  # ✅ 와일드카드 추가
    "www.${var.domain_name}"
  ]
  validation_method = "DNS"
}
```

**Route53 수정**: `terraform/route53.tf`
```hcl
# 서브도메인 레코드 추가
resource "aws_route53_record" "subdomain_a" {
  for_each = toset(["argocd", "grafana", "api"])
  
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${each.key}.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.kubernetes_ingress_v1.alb.status.0.load_balancer.0.ingress.0.hostname
    zone_id                = data.aws_lb.alb.zone_id
    evaluate_target_health = true
  }
}
```

**Ingress 수정**: 서브도메인 + Path 혼용
```yaml
# Option 1: 서브도메인 기반 (권장)
spec:
  rules:
  - host: argocd.growbin.app
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443

# Option 2: Path 기반 (현재)
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /argocd
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443

# Option 3: 혼용 (최대 유연성)
spec:
  rules:
  - host: argocd.growbin.app  # 서브도메인
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
  - host: growbin.app  # 메인 도메인 (fallback)
    http:
      paths:
      - path: /argocd
        pathType: Prefix
        backend:
          service:
            name: argocd-server
            port:
              number: 443
```

---

#### 4. Target Group Attributes 최적화
**파일**: `07-ingress-resources.yml` 수정

```yaml
annotations:
  alb.ingress.kubernetes.io/target-group-attributes: |
    deregistration_delay.timeout_seconds=30,
    stickiness.enabled=true,
    stickiness.type=lb_cookie,
    stickiness.lb_cookie.duration_seconds=86400
```

---

### 🔵 낮음 (선택사항)

#### 5. WAF 통합
**전제 조건**: AWS WAF WebACL 생성

**Terraform**: `terraform/waf.tf` (신규)
```hcl
resource "aws_wafv2_web_acl" "main" {
  name  = "${var.environment}-${var.cluster_name}-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "rate-limit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "WAF"
  }
}
```

**Ingress 수정**:
```yaml
annotations:
  alb.ingress.kubernetes.io/wafv2-acl-arn: <WAF_ACL_ARN>
```

---

#### 6. 백엔드 프로토콜 명시
```yaml
# Grafana Ingress
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP
  alb.ingress.kubernetes.io/backend-protocol-version: HTTP1

# API Ingress
annotations:
  alb.ingress.kubernetes.io/backend-protocol: HTTP
  alb.ingress.kubernetes.io/backend-protocol-version: HTTP2  # gRPC 지원
```

---

## 📊 현재 구성 점수

| 항목 | 참고 글 권장사항 | 현재 구성 | 점수 |
|------|----------------|----------|------|
| **단일 ALB 사용** | ✅ 필수 | ✅ 구현 | 10/10 |
| **Path-based Routing** | ✅ 필수 | ✅ 구현 | 10/10 |
| **SSL/TLS** | ✅ 필수 | ✅ ACM | 10/10 |
| **HTTP → HTTPS** | ✅ 권장 | ✅ ssl-redirect | 10/10 |
| **IngressClass** | ✅ 권장 (v1.22+) | ❌ annotation 사용 | 3/10 |
| **서브도메인 라우팅** | ⚠️ 선택 | ❌ 미구현 | 0/10 |
| **Health Check** | ⚠️ 선택 | ❌ 기본값 | 5/10 |
| **Target Group 최적화** | ⚠️ 선택 | ❌ 기본값 | 5/10 |
| **WAF 통합** | 🔵 선택 | ❌ 미구현 | 0/10 |
| **백엔드 프로토콜 명시** | 🔵 선택 | △ 일부 (ArgoCD만) | 6/10 |
| **총점** | - | - | **59/100** |

---

## 🎯 최종 권장사항

### ✅ 즉시 적용 (필수)

1. **IngressClass 마이그레이션** (Kubernetes 표준 준수)
2. **Health Check 커스터마이징** (장애 감지 개선)

### ⚠️ 향후 적용 (권장)

3. **서브도메인 라우팅 추가** (URL 깔끔화, CORS 간소화)
4. **Target Group Attributes 최적화** (성능 향상)

### 🔵 선택사항

5. **WAF 통합** (프로덕션 보안 강화)
6. **백엔드 프로토콜 명시** (명확성 향상)

---

## 📝 구현 계획

### Phase 1: 즉시 개선 (우선순위: 높음)
- [ ] `ansible/playbooks/07-1-ingress-class.yml` 생성
- [ ] `ansible/playbooks/07-ingress-resources.yml` 수정 (IngressClass)
- [ ] Health Check annotations 추가
- [ ] `ansible/site.yml`에 IngressClass 단계 추가

### Phase 2: 향후 개선 (우선순위: 중간)
- [ ] `terraform/acm.tf` 와일드카드 인증서 추가
- [ ] `terraform/route53.tf` 서브도메인 레코드 추가
- [ ] Ingress 서브도메인 라우팅 구현
- [ ] Target Group Attributes 최적화

### Phase 3: 선택적 개선 (우선순위: 낮음)
- [ ] `terraform/waf.tf` WAF WebACL 생성
- [ ] Ingress WAF 통합
- [ ] 백엔드 프로토콜 명시

---

## 🔗 참고 자료

1. [Kubernetes NodePort vs LoadBalancer vs Ingress](https://12bme.tistory.com/830)
2. [AWS Load Balancer Controller - Ingress Annotations](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.6/guide/ingress/annotations/)
3. [Kubernetes Ingress API - v1.22+](https://kubernetes.io/docs/concepts/services-networking/ingress/)
4. [AWS ALB - Target Group Attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html#target-group-attributes)

---

**최종 평가**: 현재 구성은 참고 글의 핵심 권장사항(단일 ALB, Path 라우팅, SSL/TLS)을 **모두 구현**했으며, **프로덕션 사용 가능**합니다. 다만, Kubernetes v1.22+ 표준(IngressClass)과 성능 최적화(Health Check, Target Group Attributes) 측면에서 개선 여지가 있습니다.

