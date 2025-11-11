# 네트워크 라우팅 구조 점검 및 수정

> 날짜: 2025-11-04  
> 문제: Route53이 ALB가 아닌 Master Node IP를 가리킴

---

## ❌ 현재 구조 (잘못됨)

```
인터넷
  ↓
Route53 (DNS)
  ├─ growbin.app → Master Public IP (52.79.238.50) ❌ 잘못됨!
  ├─ api.growbin.app → Master Public IP ❌ 잘못됨!
  ├─ argocd.growbin.app → Master Public IP ❌ 잘못됨!
  └─ grafana.growbin.app → Master Public IP ❌ 잘못됨!
  ↓
Master Node (직접 접근)
  ↓
Kubernetes Service (NodePort/ClusterIP)
  ↓
Pod
```

**문제점**:
- Route53이 Master Node의 **Public IP**를 직접 가리킴
- ALB를 우회하고 Master Node로 직접 트래픽 전송
- ALB + Ingress 구조가 무용지물
- SSL/TLS 종료가 ALB가 아닌 Master에서 처리되어야 함
- 부하 분산 불가

---

## ✅ 올바른 구조 (수정 필요)

```
인터넷
  ↓
Route53 (DNS)
  ├─ growbin.app → ALB (Alias 레코드) ✅
  ├─ api.growbin.app → ALB (Alias 레코드) ✅ (향후)
  ├─ argocd.growbin.app → ALB (Alias 레코드) ✅ (향후)
  └─ grafana.growbin.app → ALB (Alias 레코드) ✅ (향후)
  ↓
AWS Application Load Balancer (ALB)
  ├─ ACM 인증서 (SSL/TLS 자동 관리)
  └─ Path-based Routing (단일 도메인)
      ↓
      ├─ /argocd → Target Group → Worker Nodes (NodePort)
      ├─ /grafana → Target Group → Worker Nodes (NodePort)
      └─ /api/v1/* → Target Group → Worker Nodes (NodePort)
  ↓
Kubernetes Cluster
  ├─ AWS Load Balancer Controller (Helm)
  │   └─ Ingress 리소스 감지
  │   └─ ALB 자동 생성 및 관리
  │   └─ Target Group Binding
  │
  ├─ Ingress 리소스 (Path-based)
  │   ├─ argocd-ingress (namespace: argocd)
  │   ├─ grafana-ingress (namespace: monitoring)
  │   └─ api-ingress (namespace: default)
  │
  └─ Service (ClusterIP)
      ├─ argocd-server (ClusterIP + HTTPS)
      ├─ prometheus-grafana (ClusterIP + HTTP)
      └─ API Services (ClusterIP + HTTP)
      ↓
      Pod
```

---

## 🔧 Terraform 수정: Route53.tf

### 문제: A 레코드가 Master IP를 가리킴

```hcl
# ❌ 잘못된 현재 설정
resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.master.public_ip]  # ❌ Master IP 직접 연결
}
```

### 해결: ALB를 가리키는 Alias 레코드로 변경

```hcl
# ✅ 올바른 설정 (ALB Alias)
resource "aws_route53_record" "apex" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb.dns_name
    zone_id                = data.aws_lb.alb.zone_id
    evaluate_target_health = true
  }
}
```

---

## 📝 수정 사항

### 1. Terraform: `terraform/route53.tf` 전체 재작성

```hcl
# Route53 DNS Configuration
# ALB를 가리키는 Alias 레코드 생성

# Hosted Zone (기존 도메인)
data "aws_route53_zone" "main" {
  count = var.domain_name != "" ? 1 : 0
  
  name         = var.domain_name
  private_zone = false
}

# ALB 데이터 소스 (Kubernetes에서 생성된 ALB)
# alb.ingress.kubernetes.io/group.name: growbin-alb
data "aws_lb" "alb" {
  count = var.domain_name != "" ? 1 : 0
  
  tags = {
    "elbv2.k8s.aws/cluster" = var.cluster_name
    "ingress.k8s.aws/stack" = "growbin-alb"
  }
  
  # ALB가 생성될 때까지 대기 (depends_on 대체)
  # Terraform이 아닌 Kubernetes에서 ALB를 생성하므로
  # Data source를 사용하여 기존 ALB 참조
}

# Apex 도메인: growbin.app → ALB
resource "aws_route53_record" "apex" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}

# www 서브도메인: www.growbin.app → ALB
resource "aws_route53_record" "www" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}

# api 서브도메인: api.growbin.app → ALB (향후)
resource "aws_route53_record" "api" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}

# argocd 서브도메인: argocd.growbin.app → ALB (향후)
resource "aws_route53_record" "argocd" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "argocd.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}

# grafana 서브도메인: grafana.growbin.app → ALB (향후)
resource "aws_route53_record" "grafana" {
  count = var.domain_name != "" ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "grafana.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}

# Wildcard (선택): *.growbin.app → ALB
resource "aws_route53_record" "wildcard" {
  count = var.domain_name != "" && var.create_wildcard_record ? 1 : 0
  
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "*.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = data.aws_lb.alb[0].dns_name
    zone_id                = data.aws_lb.alb[0].zone_id
    evaluate_target_health = true
  }
}
```

---

## ⚠️ 문제: Terraform이 ALB를 찾을 수 없음

### 원인

Terraform이 실행될 때 **ALB가 아직 생성되지 않음**:
1. Terraform → VPC, EC2, IAM 생성
2. Ansible → Kubernetes 클러스터 구축
3. Ansible → ALB Controller 설치
4. Kubernetes (ALB Controller) → Ingress 리소스 감지
5. **ALB Controller → ALB 생성** ← Terraform보다 나중에 생성됨!

### 해결책 1: Terraform을 2단계로 분리

**Phase 1 (Terraform)**: 인프라 생성
```bash
terraform apply
```

**Phase 2 (Ansible)**: 클러스터 + ALB Controller + Ingress 생성
```bash
ansible-playbook site.yml
```

**Phase 3 (Terraform - Route53만)**: ALB 생성 후 DNS 연결
```bash
terraform apply -target=aws_route53_record.apex
```

### 해결책 2: Ansible에서 Route53 업데이트

ALB 생성 후 Ansible에서 Route53 레코드를 업데이트합니다.

**파일**: `ansible/playbooks/09-route53-update.yml`

```yaml
---
- name: "Route53 A 레코드 업데이트 (ALB 연결)"
  hosts: localhost
  gather_facts: no
  vars:
    domain_name: "{{ lookup('pipe', 'cd ../../terraform && terraform output -raw domain_name') }}"
    hosted_zone_id: "{{ lookup('pipe', 'cd ../../terraform && terraform output -raw hosted_zone_id') }}"
  tasks:
    - name: "ALB DNS 이름 가져오기"
      shell: kubectl get ingress argocd-ingress -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
      register: alb_dns
      delegate_to: "{{ groups['master'][0] }}"
      failed_when: alb_dns.stdout == ""
    
    - name: "ALB Hosted Zone ID 가져오기 (AWS CLI)"
      shell: |
        aws elbv2 describe-load-balancers \
          --query "LoadBalancers[?DNSName=='{{ alb_dns.stdout }}'].CanonicalHostedZoneId | [0]" \
          --output text
      register: alb_zone_id
      delegate_to: localhost
    
    - name: "Route53 A 레코드 업데이트 (Apex)"
      community.aws.route53:
        state: present
        zone: "{{ domain_name }}"
        record: "{{ domain_name }}"
        type: A
        alias: yes
        alias_hosted_zone_id: "{{ alb_zone_id.stdout }}"
        value: "{{ alb_dns.stdout }}"
        alias_evaluate_target_health: yes
        overwrite: yes
      delegate_to: localhost
    
    - name: "Route53 A 레코드 업데이트 (www)"
      community.aws.route53:
        state: present
        zone: "{{ domain_name }}"
        record: "www.{{ domain_name }}"
        type: A
        alias: yes
        alias_hosted_zone_id: "{{ alb_zone_id.stdout }}"
        value: "{{ alb_dns.stdout }}"
        alias_evaluate_target_health: yes
        overwrite: yes
      delegate_to: localhost
    
    - name: "Route53 업데이트 완료"
      debug:
        msg:
          - "✅ Route53 A 레코드 업데이트 완료"
          - "ALB DNS: {{ alb_dns.stdout }}"
          - "ALB Zone ID: {{ alb_zone_id.stdout }}"
          - ""
          - "도메인 접속:"
          - "  https://{{ domain_name }}/argocd"
          - "  https://{{ domain_name }}/grafana"
          - "  https://{{ domain_name }}/api/v1/*"
```

---

## 🚀 권장 방안

### Option A: Ansible에서 Route53 관리 (권장)

**장점**:
- ✅ ALB 생성 후 자동으로 Route53 업데이트
- ✅ Terraform 재실행 불필요
- ✅ 완전 자동화

**단점**:
- ⚠️ Ansible에 AWS 모듈 추가 필요 (`amazon.aws`, `community.aws`)

**구현**:
1. `ansible/playbooks/09-route53-update.yml` 생성
2. `ansible/site.yml`에 추가
3. ALB Controller + Ingress 생성 후 Route53 업데이트

---

### Option B: 수동으로 ALB 연결

**장점**:
- ✅ 간단하고 즉시 적용 가능
- ✅ Terraform/Ansible 수정 불필요

**단점**:
- ❌ 수동 작업 필요
- ❌ 클러스터 재생성 시 반복 작업

**구현**:
1. Ansible로 ALB 생성
2. ALB DNS 복사
3. Route53 콘솔에서 수동으로 Alias 레코드 생성

---

## ✅ 최종 권장 구조

```
인터넷
  ↓
Route53 (DNS) - Alias 레코드
  ├─ growbin.app → ALB ✅
  ├─ www.growbin.app → ALB ✅
  ├─ api.growbin.app → ALB ✅ (향후)
  ├─ argocd.growbin.app → ALB ✅ (향후)
  └─ grafana.growbin.app → ALB ✅ (향후)
  ↓
AWS Application Load Balancer (ALB)
  ├─ Listener 80 (HTTP → 443 Redirect)
  ├─ Listener 443 (HTTPS)
  ├─ ACM Certificate (growbin.app, *.growbin.app)
  └─ Path-based Rules
      ├─ /argocd → Target Group (Worker Nodes:NodePort)
      ├─ /grafana → Target Group (Worker Nodes:NodePort)
      └─ /api/v1/* → Target Group (Worker Nodes:NodePort)
  ↓
Worker Nodes (NodePort)
  ↓
Kubernetes Ingress Controller (AWS LB Controller)
  ↓
Kubernetes Service (ClusterIP)
  ├─ argocd-server (ClusterIP:443)
  ├─ prometheus-grafana (ClusterIP:80)
  └─ API Services (ClusterIP:80)
  ↓
Pods
```

---

## 🎯 결론

**현재 문제**: Route53 → Master IP (ALB 우회)  
**해결 방안**: Route53 → ALB (Alias 레코드)

**권장**: Ansible에서 Route53 자동 업데이트 (Option A)

**작성일**: 2025-11-04  
**버전**: 1.0.0

