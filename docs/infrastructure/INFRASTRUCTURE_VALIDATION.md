# 인프라 핵심 구성요소 검증 체크리스트

Phase 1&2 배포를 위한 인프라 구성 검증 리포트

## ✅ 검증 완료 항목

### 1. AWS Load Balancer (ALB) ✅

**위치**: `terraform/alb-controller-iam.tf`

#### IAM Policy 설정
- ✅ AWS 공식 ALB Controller IAM Policy 적용
- ✅ ELB 생성/수정/삭제 권한
- ✅ Target Group 관리 권한
- ✅ Listener & Rule 관리 권한
- ✅ ACM 인증서 연동 권한
- ✅ Security Group 관리 권한
- ✅ WAF/Shield 통합 권한

```hcl
resource "aws_iam_policy" "alb_controller" {
  name        = "${var.environment}-alb-controller-policy"
  description = "IAM policy for AWS Load Balancer Controller"
  # AWS 공식 정책 (258 lines)
}

resource "aws_iam_role_policy_attachment" "alb_controller" {
  role       = aws_iam_role.k8s_node.name
  policy_arn = aws_iam_policy.alb_controller.arn
}
```

#### 주요 권한
- `elasticloadbalancing:*` - ALB/NLB 전체 관리
- `ec2:*SecurityGroup*` - Security Group 관리
- `acm:*Certificate*` - SSL/TLS 인증서
- `wafv2:*` - WAF 통합
- `shield:*` - DDoS 보호

---

### 2. Route53 DNS ✅

**위치**: `terraform/route53.tf`, `terraform/acm.tf`

#### Hosted Zone 설정
```hcl
data "aws_route53_zone" "main" {
  count = var.domain_name != "" ? 1 : 0
  name         = var.domain_name  # growbin.app
  private_zone = false
}
```

#### DNS 레코드 (Ansible에서 관리)
- ✅ `growbin.app` → ALB (Apex 도메인)
- ✅ `www.growbin.app` → ALB
- ✅ `api.growbin.app` → ALB
  - `/auth` → Auth API
  - `/my` → My API
  - `/scan` → Scan API
  - `/character` → Character API
  - `/location` → Location API
- ✅ `argocd.growbin.app` → ALB
- ✅ `grafana.growbin.app` → ALB
- ✅ `images.growbin.app` → CloudFront (CDN)

**Ansible 위치**: `ansible/playbooks/09-route53-update.yml`

**라우팅 방식**: 
- API: 서브도메인 + Path (`api.growbin.app/auth`)
- 관리 도구: 서브도메인 (`argocd.growbin.app`, `grafana.growbin.app`)
- CDN: 서브도메인 (`images.growbin.app`)

#### ACM 인증서 (ALB용)
```hcl
resource "aws_acm_certificate" "main" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
  
  # ap-northeast-2 (Seoul)
}
```

- ✅ Wildcard 인증서: `*.growbin.app`
- ✅ DNS 자동 검증
- ✅ ALB에서 TLS 종료

---

### 3. CloudFront CDN ✅

**위치**: `terraform/cloudfront.tf`

#### CDN Distribution 설정
```hcl
resource "aws_cloudfront_distribution" "images" {
  enabled             = true
  is_ipv6_enabled     = true
  price_class         = "PriceClass_200"  # 아시아 + 북미 + 유럽
  aliases             = ["images.${var.domain_name}"]
}
```

#### 주요 기능
- ✅ S3 Origin Access Identity (OAI) 보안 연결
- ✅ HTTPS 강제 리디렉션
- ✅ 이미지 최적화 캐싱 (TTL: 24시간)
- ✅ GZIP/Brotli 압축
- ✅ Custom Domain: `images.growbin.app`

#### ACM 인증서 (CloudFront용)
```hcl
resource "aws_acm_certificate" "cdn" {
  provider          = aws.us_east_1  # CloudFront는 us-east-1 필수!
  domain_name       = "images.${var.domain_name}"
  validation_method = "DNS"
}
```

- ✅ **US-EAST-1 리전** (CloudFront 요구사항)
- ✅ `images.growbin.app` 전용 인증서
- ✅ TLSv1.2_2021 최소 프로토콜

#### Route53 연동
```hcl
resource "aws_route53_record" "cdn" {
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "images.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = aws_cloudfront_distribution.images.domain_name
    zone_id                = aws_cloudfront_distribution.images.hosted_zone_id
    evaluate_target_health = false
  }
}
```

---

### 4. S3 이미지 스토리지 ✅

**위치**: `terraform/s3.tf`

#### Bucket 설정
```hcl
resource "aws_s3_bucket" "images" {
  bucket = "${var.environment}-${var.cluster_name}-images"
  # prod-sesacthon-images
}
```

#### 보안 설정
- ✅ Public Access Block (전체 차단)
- ✅ CloudFront OAI만 액세스 허용
- ✅ Server-Side Encryption (AES-256)
- ✅ Versioning 활성화

#### Lifecycle 정책
```hcl
resource "aws_s3_bucket_lifecycle_configuration" "images" {
  rule {
    id = "cleanup-old-images"
    
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    
    expiration {
      days = 90
    }
  }
}
```

- 30일 후: Standard-IA (비용 절감)
- 90일 후: 자동 삭제

#### CORS 설정 (프론트엔드 업로드)
```hcl
cors_rule {
  allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
  allowed_origins = [
    "https://${var.domain_name}",
    "https://www.${var.domain_name}",
    "http://localhost:3000"
  ]
}
```

---

### 5. Kubernetes Ingress (ALB) ✅

**위치**: 
- `charts/ecoeco-backend/templates/ingress.yaml`
- `charts/ecoeco-backend/values-phase12.yaml`

#### Ingress Class
```yaml
ingressClassName: alb
```

#### ALB Annotations
```yaml
annotations:
  alb.ingress.kubernetes.io/scheme: internet-facing
  alb.ingress.kubernetes.io/target-type: instance
  alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
  alb.ingress.kubernetes.io/ssl-redirect: '443'
```

- ✅ HTTP → HTTPS 자동 리디렉션
- ✅ Instance 타겟 모드 (NodePort 사용)
- ✅ Internet-facing ALB

#### API 라우팅 (Phase 1&2)
```yaml
host: api.growbin.app
paths:
  - path: /auth
    service: auth-api
  - path: /my
    service: my-api
  - path: /scan
    service: scan-api
  - path: /character
    service: character-api
  - path: /location
    service: location-api
```

**서브도메인 + Path routing**: API는 `api.growbin.app` 서브도메인 아래 경로로 구분

#### Health Check
```yaml
alb.ingress.kubernetes.io/healthcheck-path: /health
alb.ingress.kubernetes.io/healthcheck-interval-seconds: '15'
alb.ingress.kubernetes.io/healthcheck-timeout-seconds: '5'
alb.ingress.kubernetes.io/healthy-threshold-count: '2'
alb.ingress.kubernetes.io/unhealthy-threshold-count: '2'
```

---

### 6. Calico CNI (VXLAN Always, BGP Off) ✅

**위치**: `ansible/playbooks/04-cni-install.yml`

#### 설치 버전
```yaml
# Calico v3.26.4 (2024 LTS)
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.4/manifests/calico.yaml
```

#### VXLAN Always 설정
```yaml
kubectl patch ippool default-ipv4-ippool --type=merge --patch='
{
  "spec": {
    "ipipMode": "Never",
    "vxlanMode": "Always",
    "natOutgoing": true
  }
}'
```

- ✅ **VXLAN Always**: 모든 Pod 간 통신에 VXLAN 사용
- ✅ **IPIP Never**: IP-in-IP 터널링 비활성화
- ✅ **NAT Outgoing**: 외부 통신 시 SNAT 적용

#### BGP 완전 비활성화
```yaml
apiVersion: crd.projectcalico.org/v1
kind: BGPConfiguration
metadata:
  name: default
spec:
  nodeToNodeMeshEnabled: false
  asNumber: 64512
```

- ✅ Node-to-Node BGP Mesh 비활성화
- ✅ BGP 피어링 없음 (VXLAN 전용)

#### Felix 설정
```yaml
apiVersion: crd.projectcalico.org/v1
kind: FelixConfiguration
metadata:
  name: default
spec:
  bpfEnabled: false
  ipipEnabled: false
  vxlanEnabled: true
```

- ✅ eBPF 비활성화 (일반 iptables 사용)
- ✅ IPIP 비활성화
- ✅ VXLAN 활성화

#### BIRD Probe 제거
```yaml
kubectl patch daemonset calico-node -n kube-system --type=json -p='[
  {
    "op": "replace",
    "path": "/spec/template/spec/containers/0/livenessProbe/exec/command",
    "value": ["/bin/calico-node", "-felix-live"]
  },
  {
    "op": "replace",
    "path": "/spec/template/spec/containers/0/readinessProbe/exec/command",
    "value": ["/bin/calico-node", "-felix-ready"]
  }
]'
```

- ✅ BIRD (BGP daemon) Liveness/Readiness 체크 제거
- ✅ Felix만 체크 (VXLAN 모드에서 BIRD 불필요)

#### 환경변수 설정
```bash
kubectl set env daemonset/calico-node -n kube-system \
  CLUSTER_TYPE=k8s \
  CALICO_IPV4POOL_IPIP=Never \
  CALICO_IPV4POOL_VXLAN=Always \
  FELIX_IPIPENABLED=false \
  FELIX_VXLANENABLED=true
```

---

## 📊 네트워크 아키텍처 요약

### 외부 → 클러스터 트래픽

```
┌─────────────────────────────────────────────────────┐
│  1. 사용자 요청                                      │
│     https://api.growbin.app/auth/login              │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  2. Route53 DNS 조회                                │
│     api.growbin.app → ALB DNS (A Record Alias)      │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  3. ALB (Application Load Balancer)                 │
│     - ACM 인증서로 TLS 종료                         │
│     - Host + Path 라우팅:                           │
│       api.growbin.app/auth → auth-api               │
│       argocd.growbin.app → argocd-server            │
│       grafana.growbin.app → grafana                 │
│     - Health Check: /health                         │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  4. Kubernetes Service (NodePort)                   │
│     - Service Type: NodePort                        │
│     - Target: k8s-api-auth 노드                     │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  5. Auth API Pod                                    │
│     - nodeSelector: domain=auth                     │
│     - 컨테이너 포트: 8000                           │
└─────────────────────────────────────────────────────┘
```

### Pod 간 통신 (Calico VXLAN)

```
┌─────────────────────────────────────────────────────┐
│  Auth API Pod (Node A)                              │
│  10.244.1.10                                        │
└─────────────────────────────────────────────────────┘
                    ↓ VXLAN Tunnel
┌─────────────────────────────────────────────────────┐
│  PostgreSQL Pod (Node B)                            │
│  10.244.2.20                                        │
└─────────────────────────────────────────────────────┘

- VXLAN Always: 모든 Pod 간 통신은 VXLAN 오버레이
- BGP Off: BGP 라우팅 없음
- NAT Outgoing: 외부 통신 시 Node IP로 SNAT
```

### CDN 트래픽 (이미지)

```
┌─────────────────────────────────────────────────────┐
│  1. 프론트엔드 이미지 요청                           │
│     https://images.growbin.app/uploads/photo.jpg    │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  2. Route53 DNS                                     │
│     images.growbin.app → CloudFront (A Alias)       │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│  3. CloudFront Edge (Seoul)                         │
│     - Cache Hit: 즉시 반환 (< 10ms)                │
│     - Cache Miss: S3 Origin 조회                    │
└─────────────────────────────────────────────────────┘
                    ↓ (Cache Miss 시)
┌─────────────────────────────────────────────────────┐
│  4. S3 Bucket (prod-sesacthon-images)               │
│     - OAI 인증 (CloudFront만 액세스)                │
│     - 이미지 반환 + CloudFront 캐싱                 │
└─────────────────────────────────────────────────────┘
```

---

## 🔐 보안 체크리스트

### TLS/SSL
- ✅ ALB: ACM 인증서 (ap-northeast-2)
- ✅ CloudFront: ACM 인증서 (us-east-1)
- ✅ Wildcard 인증서: `*.growbin.app`
- ✅ Minimum TLS: 1.2

### IAM & 권한
- ✅ ALB Controller IAM Policy (AWS 공식)
- ✅ EC2 Instance Profile 연결
- ✅ S3 OAI (CloudFront 전용 액세스)

### 네트워크
- ✅ Security Group: ALB → NodePort 허용
- ✅ S3 Public Access Block (전체 차단)
- ✅ CloudFront Origin: Private S3

### 인증서 갱신
- ✅ ACM 자동 갱신 (90일 전 알림)
- ✅ DNS 검증 레코드 유지

---

## 📝 Terraform Outputs

```hcl
# DNS 레코드
output "dns_records" {
  value = {
    apex_domain = "https://growbin.app"
    api_base    = "https://api.growbin.app"
    auth_url    = "https://api.growbin.app/auth"
    my_url      = "https://api.growbin.app/my"
    scan_url    = "https://api.growbin.app/scan"
    argocd_url  = "https://argocd.growbin.app"
    grafana_url = "https://grafana.growbin.app"
    cdn_url     = "https://images.growbin.app"
  }
}

# CloudFront
output "cloudfront_info" {
  value = {
    distribution_id = aws_cloudfront_distribution.images.id
    cdn_url        = "https://images.growbin.app"
  }
}

# S3
output "s3_bucket_info" {
  value = {
    bucket_name = "prod-sesacthon-images"
    region      = "ap-northeast-2"
  }
}
```

---

## ✅ 최종 검증 결과

### Infrastructure as Code (Terraform)
- ✅ ALB Controller IAM Policy
- ✅ Route53 Hosted Zone & ACM 인증서
- ✅ CloudFront Distribution + OAI
- ✅ S3 Bucket + Lifecycle + CORS
- ✅ VPC + Security Groups
- ✅ EC2 Instances (Phase 1&2)

### Kubernetes Configuration (Ansible)
- ✅ Calico CNI (VXLAN Always, BGP Off)
- ✅ ALB Ingress Controller 설치
- ✅ CoreDNS 설정
- ✅ kube-proxy 설정

### GitOps Pipeline (Helm + ArgoCD)
- ✅ Ingress 리소스 (ALB annotations)
- ✅ API Service/Deployment
- ✅ Health Check 설정
- ✅ Resource Limits

---

## 🎯 배포 준비 완료!

모든 핵심 인프라 구성요소가 올바르게 설정되었습니다.

### 배포 순서

1. **Terraform Apply**
   ```bash
   cd scripts/cluster
   ./auto-rebuild.sh
   ```
   - VPC, EC2, S3, CloudFront, Route53 생성

2. **Ansible Playbook**
   ```bash
   # auto-rebuild.sh에서 자동 실행
   ansible-playbook -i terraform/hosts ansible/site.yml
   ```
   - Kubernetes 클러스터 구성
   - Calico CNI 설치 (VXLAN Always)
   - ALB Controller 설치

3. **ArgoCD 배포**
   ```bash
   kubectl apply -f argocd/applications/ecoeco-backend-phase12.yaml
   ```
   - API Deployments
   - Ingress (ALB 생성)

4. **Route53 업데이트** (Ansible 자동)
   ```bash
   # ALB DNS 조회 후 Route53 업데이트
   ansible-playbook ansible/playbooks/09-route53-update.yml
   ```

---

## 🔍 배포 후 검증

### 1. ALB 생성 확인
```bash
kubectl get ingress -A
aws elbv2 describe-load-balancers --region ap-northeast-2
```

### 2. DNS 전파 확인
```bash
dig api.growbin.app
dig argocd.growbin.app
dig grafana.growbin.app
dig images.growbin.app

# ALB 연결 확인
dig api.growbin.app +short
```

### 3. HTTPS 접속 테스트
```bash
curl -I https://api.growbin.app/auth/health
curl -I https://argocd.growbin.app
curl -I https://grafana.growbin.app
curl -I https://images.growbin.app
```

### 4. Calico 상태 확인
```bash
kubectl get pods -n kube-system -l k8s-app=calico-node
calicoctl get ippool -o yaml
calicoctl get bgpconfig -o yaml
```

### 5. CloudFront 캐시 확인
```bash
# X-Cache 헤더 확인 (Hit/Miss)
curl -I https://images.growbin.app/test.jpg
```

---

**모든 구성요소가 프로덕션 배포 준비 완료! 🚀**

