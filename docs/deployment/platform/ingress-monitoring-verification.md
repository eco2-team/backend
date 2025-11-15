# Ingress & Monitoring 리소스 설정 확인 (14-Node)

## ✅ 확인 완료

### 1️⃣ Prometheus 리소스 설정 ✅

**파일**: `k8s/monitoring/prometheus-deployment.yaml`

```yaml
resources:
  requests:
    cpu: 500m      # ✅ 0.5 vCPU (요청한 대로)
    memory: 1Gi
  limits:
    cpu: 1000m     # 1 vCPU (버스트 가능)
    memory: 2Gi
```

**k8s-monitoring 노드 리소스 분배**:
```yaml
노드: t3.medium (2 vCPU, 4GB RAM)

Pod별 할당:
  - Prometheus: 0.5 vCPU (request) / 1.0 vCPU (limit)
  - Grafana: 0.2 vCPU / 0.5 vCPU
  - Atlantis: 0.25 vCPU / 1.0 vCPU
  - System: ~0.5 vCPU

총 Request: 1.45 vCPU / 2 vCPU (72% 사용)
총 Limit: 2.5 vCPU / 2 vCPU (버스트 시 경합)
```

---

### 2️⃣ Ingress 통합 설정 ✅

**새 파일**: `k8s/ingress/14-nodes-ingress.yaml`

#### 단일 ALB로 통합 (ecoeco-main group)

```yaml
1. api.growbin.app (Order: 10)
   ├── /api/v1/auth → auth-api:8000
   ├── /api/v1/my → my-api:8000
   ├── /api/v1/scan → scan-api:8000
   ├── /api/v1/character → character-api:8000
   ├── /api/v1/location → location-api:8000
   ├── /api/v1/info → info-api:8000
   └── /api/v1/chat → chat-api:8000

2. atlantis.growbin.app (Order: 20)
   └── / → atlantis:80

3. grafana.growbin.app (Order: 30)
   └── / → grafana:3000

4. prometheus.growbin.app (Order: 40)
   └── / → prometheus:9090
```

#### 주요 설정

```yaml
공통:
  - Class: ALB (AWS Application Load Balancer)
  - Scheme: internet-facing
  - Target Type: IP
  - SSL Redirect: HTTP → HTTPS
  - ACM Certificate: arn:aws:acm:...:certificate/CERT_ID

Health Check:
  - API: /health (30s interval)
  - Atlantis: /healthz (30s interval)
  - Grafana: /api/health (30s interval)
  - Prometheus: /-/healthy (30s interval)

특수 설정:
  - Atlantis: backend-protocol-timeout=300 (GitHub Webhook)
```

---

## 📊 리소스 요약

### k8s-monitoring 노드 (t3.medium)

| Pod | CPU Request | CPU Limit | Memory Request | Memory Limit | 비고 |
|-----|-------------|-----------|----------------|--------------|------|
| **Prometheus** | **500m (0.5 vCPU)** | **1000m (1 vCPU)** | **1Gi** | **2Gi** | ✅ 요청 사항 |
| Grafana | 200m | 500m | 512Mi | 1Gi | Monitoring UI |
| Atlantis | 250m | 1000m | 512Mi | 2Gi | GitOps |
| **합계** | **950m** | **2500m** | **2Gi** | **5Gi** | - |
| 노드 용량 | 2000m | 2000m | 4Gi | 4Gi | - |
| **여유** | **1050m (52%)** | **-500m (초과)** | **2Gi (50%)** | **-1Gi (초과)** | Limit 초과는 OK |

**참고**:
- Request는 노드 용량 내에 있어야 함 ✅ (950m < 2000m)
- Limit는 초과 가능 (버스트 시 경합) ⚠️
- 실제 사용량은 Request와 Limit 사이

---

## 🚀 배포 가이드

### Step 1: Ingress 배포

```bash
# Ingress 리소스 생성
kubectl apply -f k8s/ingress/14-nodes-ingress.yaml

# 배포 확인
kubectl get ingress -A
kubectl describe ingress api-ingress -n api
kubectl describe ingress atlantis-ingress -n atlantis
kubectl describe ingress grafana-ingress -n monitoring
kubectl describe ingress prometheus-ingress -n monitoring

# ALB 생성 확인 (약 3-5분 소요)
kubectl get ingress api-ingress -n api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Step 2: Route53 설정

```bash
# ALB DNS 확인
ALB_DNS=$(kubectl get ingress api-ingress -n api -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "ALB DNS: $ALB_DNS"

# Route53에 A Record (Alias) 생성
# 1. api.growbin.app → $ALB_DNS (Alias)
# 2. atlantis.growbin.app → $ALB_DNS (Alias)
# 3. grafana.growbin.app → $ALB_DNS (Alias)
# 4. prometheus.growbin.app → $ALB_DNS (Alias)
```

**Terraform으로 자동화** (권장):
```hcl
# Route53 Records
data "kubernetes_ingress_v1" "api" {
  metadata {
    name      = "api-ingress"
    namespace = "api"
  }
}

resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.growbin.app"
  type    = "A"
  
  alias {
    name                   = data.kubernetes_ingress_v1.api.status[0].load_balancer[0].ingress[0].hostname
    zone_id                = data.aws_elb_hosted_zone_id.main.id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "atlantis" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "atlantis.growbin.app"
  type    = "A"
  
  alias {
    name                   = data.kubernetes_ingress_v1.api.status[0].load_balancer[0].ingress[0].hostname
    zone_id                = data.aws_elb_hosted_zone_id.main.id
    evaluate_target_health = true
  }
}

# grafana, prometheus도 동일
```

### Step 3: ACM Certificate 설정

```bash
# ACM Certificate 생성 (AWS Console 또는 Terraform)
# 도메인: *.growbin.app (와일드카드)
# 검증: DNS (Route53 자동)

# Certificate ARN 확인
aws acm list-certificates --region ap-northeast-2

# Ingress YAML 업데이트
# alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:...:certificate/CERT_ID
```

### Step 4: 접근 테스트

```bash
# API 테스트
curl -k https://api.growbin.app/health
curl -k https://api.growbin.app/api/v1/auth/health

# Atlantis 테스트
curl -k https://atlantis.growbin.app/healthz

# Grafana 테스트
curl -k https://grafana.growbin.app/api/health

# Prometheus 테스트
curl -k https://prometheus.growbin.app/-/healthy
```

---

## 🔧 Prometheus 리소스 조정 (필요 시)

### 현재 설정 (확인 완료)

```yaml
# k8s/monitoring/prometheus-deployment.yaml
resources:
  requests:
    cpu: 500m      # ✅ 0.5 vCPU
    memory: 1Gi
  limits:
    cpu: 1000m     # 1 vCPU (버스트)
    memory: 2Gi
```

### 모니터링

```bash
# Prometheus Pod 리소스 사용량 확인
kubectl top pod -n monitoring prometheus-xxxxx

# 예상 출력:
# NAME              CPU(cores)   MEMORY(bytes)
# prometheus-xxxxx  450m         850Mi

# 로그 확인
kubectl logs -n monitoring prometheus-xxxxx -f
```

### 스케일링 (필요 시)

```yaml
# 리소스 부족 시 증가
resources:
  requests:
    cpu: 750m      # 0.75 vCPU
    memory: 1.5Gi
  limits:
    cpu: 1500m     # 1.5 vCPU
    memory: 3Gi

# 또는 노드 업그레이드
# t3.medium (2 vCPU, 4GB) → t3.large (2 vCPU, 8GB)
```

---

## 📝 체크리스트

### Prometheus 리소스
- [x] ✅ CPU Request: 500m (0.5 vCPU) - 확인 완료
- [x] ✅ CPU Limit: 1000m (1 vCPU)
- [x] ✅ Memory Request: 1Gi
- [x] ✅ Memory Limit: 2Gi
- [x] ✅ NodeSelector: node-role=infra (또는 workload=monitoring)
- [x] ✅ PVC: 50Gi (gp3)

### Ingress 설정
- [x] ✅ API Ingress 생성 (api.growbin.app)
- [x] ✅ Atlantis Ingress 생성 (atlantis.growbin.app)
- [x] ✅ Grafana Ingress 생성 (grafana.growbin.app)
- [x] ✅ Prometheus Ingress 생성 (prometheus.growbin.app)
- [x] ✅ 단일 ALB 그룹 (ecoeco-main)
- [x] ✅ Health Check 설정
- [x] ✅ SSL Redirect (HTTP → HTTPS)
- [ ] 🔲 ACM Certificate ARN 업데이트 (실제 ARN 필요)
- [ ] 🔲 Route53 A Record 생성 (배포 후)

---

## 🎯 요약

### 확인 완료 사항

```yaml
1. Prometheus 리소스:
   ✅ CPU: 500m (0.5 vCPU) - 요청한 대로 설정됨
   ✅ Memory: 1Gi
   ✅ k8s-monitoring 노드 배치

2. Ingress 통합:
   ✅ 4개 도메인 단일 ALB로 통합
   ✅ api.growbin.app (7 APIs)
   ✅ atlantis.growbin.app (GitOps)
   ✅ grafana.growbin.app (Monitoring)
   ✅ prometheus.growbin.app (Monitoring)
```

### 다음 단계

```bash
1. 🔲 ACM Certificate 생성 (*.growbin.app)
2. 🔲 Ingress 배포 (kubectl apply)
3. 🔲 Route53 A Record 생성
4. 🔲 접근 테스트
5. 🔲 Prometheus 리소스 모니터링
```

---

**작성일**: 2025-11-08  
**상태**: ✅ 확인 완료 (Prometheus 0.5 vCPU, Ingress 통합)  
**다음**: ACM Certificate 생성 → Ingress 배포 → Route53 설정

