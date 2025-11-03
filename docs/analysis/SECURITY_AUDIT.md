# 보안 감사 보고서: RBAC 및 네트워크 정책

## 📋 개요

현재 Kubernetes 클러스터의 RBAC 및 네트워크 정책 보안 상태를 감사한 결과입니다.

**감사 일자**: 2025-11-03  
**클러스터**: Self-Managed Kubernetes (v1.28.4)  
**인프라**: AWS EC2 (Master, Worker-1, Worker-2, Storage)

---

## 🔴 치명적 취약점 (Critical)

### 1. Kubernetes API Server 공개 접근

**위치**: `terraform/modules/security-groups/main.tf:16-22`

```terraform
# Kubernetes API Server
ingress {
  description = "Kubernetes API"
  from_port   = 6443
  to_port     = 6443
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]  # ❌ 전 세계 모든 IP에서 접근 가능
}
```

**위험도**: 🔴 **CRITICAL**

**설명**:
- Kubernetes API Server (포트 6443)가 전 세계 모든 IP(`0.0.0.0/0`)에서 접근 가능합니다.
- 인증 없이 또는 약한 인증으로 API 서버에 접근 가능할 경우, 전체 클러스터를 제어할 수 있습니다.
- 공격자는 Pod 생성, Secret 탈취, 전체 클러스터 파괴 등을 시도할 수 있습니다.

**권장 조치**:
```terraform
# 권장 설정
ingress {
  description = "Kubernetes API"
  from_port   = 6443
  to_port     = 6443
  protocol    = "tcp"
  cidr_blocks = [
    "10.0.0.0/8",          # VPC 내부
    "YOUR_OFFICE_IP/32",   # 사무실 IP
    "YOUR_VPN_IP/32"       # VPN IP
  ]
}
```

**추가 보안 조치**:
- ✅ Kubernetes API Server 인증 강화 (TLS 인증서 검증)
- ✅ RBAC 정책 엄격하게 설정
- ✅ NetworkPolicy로 Pod 간 통신 제한
- ✅ AWS WAF 또는 CloudFront로 API 서버 보호 (선택)

---

### 2. NodePort 서비스 공개 접근

**위치**: `terraform/modules/security-groups/main.tf:78-85`

```terraform
# NodePort Services (선택)
ingress {
  description = "NodePort Services"
  from_port   = 30000
  to_port     = 32767
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]  # ❌ 전 세계 모든 IP에서 접근 가능
}
```

**위험도**: 🔴 **CRITICAL**

**설명**:
- NodePort 범위(30000-32767)가 전 세계 모든 IP에서 접근 가능합니다.
- 실수로 또는 악의적으로 NodePort 서비스를 생성하면, 클러스터 내부 서비스가 인터넷에 노출될 수 있습니다.
- 특히 데이터베이스, 메시지 큐, 관리 인터페이스가 노출되면 심각한 데이터 유출 위험이 있습니다.

**권장 조치**:
```terraform
# NodePort는 ALB Controller를 통해서만 접근 허용
# NodePort 직접 접근은 차단
# 이 ingress rule 제거 또는 제한
```

**대안**:
- ✅ ALB Controller + Ingress 사용 (권장)
- ✅ LoadBalancer Service 타입 사용
- ✅ NodePort는 내부 통신용으로만 사용

---

### 3. Master → Worker 전체 트래픽 허용

**위치**: `terraform/modules/security-groups/main.tf:215-223`

```terraform
resource "aws_security_group_rule" "master_to_worker_all" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 0
  protocol                 = "-1"  # ❌ 모든 프로토콜, 모든 포트
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.master.id
  description              = "All traffic from master"
}
```

**위험도**: 🔴 **CRITICAL**

**설명**:
- Master 노드에서 Worker 노드로 모든 프로토콜, 모든 포트의 트래픽이 허용됩니다.
- Master 노드가 침해되면 Worker 노드의 모든 리소스에 접근 가능합니다.
- Defense-in-Depth 원칙 위반: 계층별 방어가 없습니다.

**권장 조치**:
```terraform
# 필요한 포트만 명시적으로 허용
resource "aws_security_group_rule" "master_to_worker_kubelet" {
  type                     = "ingress"
  from_port                = 10250  # Kubelet API만
  to_port                  = 10250
  protocol                 = "tcp"
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.master.id
  description              = "Kubelet API from master"
}

resource "aws_security_group_rule" "master_to_worker_metrics" {
  type                     = "ingress"
  from_port                = 10255  # Metrics (필요시)
  to_port                  = 10255
  protocol                 = "tcp"
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.master.id
  description              = "Metrics from master"
}
```

---

## 🟠 높은 위험 (High)

### 4. NetworkPolicy 부재

**위치**: 전체 클러스터

**현재 상태**:
- ❌ NetworkPolicy 리소스가 전혀 없습니다.
- ❌ 모든 Pod가 모든 Pod와 통신 가능합니다.
- ❌ Namespace 간 격리가 없습니다.

**위험도**: 🟠 **HIGH**

**설명**:
- 기본적으로 Kubernetes는 모든 Pod 간 통신을 허용합니다.
- 한 Pod가 침해되면 클러스터 내 모든 Pod에 접근 가능합니다.
- 특히 데이터베이스(RabbitMQ, Redis)가 모든 Pod에서 접근 가능합니다.

**권장 조치**:

#### 4.1 RabbitMQ 네트워크 정책

```yaml
# ansible/roles/rabbitmq/files/network-policy.yml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: rabbitmq-network-policy
  namespace: messaging
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: rabbitmq
  policyTypes:
  - Ingress
  ingress:
  # Application Pods에서만 접근 허용
  - from:
    - namespaceSelector:
        matchLabels:
          name: default  # 또는 application namespace
      podSelector:
        matchLabels:
          app: fastapi  # FastAPI Pod만
    ports:
    - protocol: TCP
      port: 5672  # AMQP
    - protocol: TCP
      port: 15672  # Management UI
  # RabbitMQ Operator는 허용
  - from:
    - podSelector:
        matchLabels:
          app.kubernetes.io/name: rabbitmq-cluster-operator
    ports:
    - protocol: TCP
      port: 5672
```

#### 4.2 Redis 네트워크 정책

```yaml
# ansible/roles/redis/files/network-policy.yml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: redis-network-policy
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: redis
  policyTypes:
  - Ingress
  ingress:
  # FastAPI 및 Celery Worker만 허용
  - from:
    - podSelector:
        matchLabels:
          app: fastapi
    ports:
    - protocol: TCP
      port: 6379
  - from:
    - podSelector:
        matchLabels:
          app: celery-worker
    ports:
    - protocol: TCP
      port: 6379
```

#### 4.3 기본 거부 정책 (Default Deny)

```yaml
# ansible/roles/common/files/default-network-policy.yml
# 모든 Namespace에 적용
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: <namespace>
spec:
  podSelector: {}  # 모든 Pod
  policyTypes:
  - Ingress
  - Egress
  # 명시적으로 허용된 정책이 없으면 모든 통신 차단
```

---

### 5. RBAC 정책 부재

**위치**: 전체 클러스터

**현재 상태**:
- ❌ 명시적인 RBAC 정책이 없습니다.
- ❌ 모든 Pod가 `default` ServiceAccount 사용 가능.
- ❌ Pod가 클러스터 리소스에 접근할 수 있는 권한이 명확하지 않습니다.

**위험도**: 🟠 **HIGH**

**설명**:
- 기본적으로 Pod는 `default` ServiceAccount를 사용하며, 이는 클러스터 리소스에 접근 권한이 없습니다.
- 하지만 애플리케이션 Pod가 필요 이상의 권한을 가지거나, ServiceAccount가 명시적으로 정의되지 않으면 보안 위험이 있습니다.

**권장 조치**:

#### 5.1 Pod Security Standards 활성화

```yaml
# Master 노드에서 실행
apiVersion: apiserver.config.k8s.io/v1
kind: AdmissionConfiguration
plugins:
- name: PodSecurity
  configuration:
    apiVersion: pod-security.admission.config.k8s.io/v1
    kind: PodSecurityConfiguration
    defaults:
      enforce: "baseline"
      audit: "restricted"
      warn: "restricted"
    exemptions:
      usernames: []  # 시스템 사용자 제외
      runtimeClasses: []
      namespaces:
      - kube-system
      - kube-public
      - kube-node-lease
```

#### 5.2 애플리케이션별 ServiceAccount 생성

```yaml
# FastAPI ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fastapi-sa
  namespace: default
  annotations:
    # AWS IAM Role (IRSA 대체 - Self-Managed에서는 직접 구현 필요)
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/fastapi-role
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: fastapi-role
  namespace: default
rules:
# 필요한 권한만 부여
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: fastapi-rolebinding
  namespace: default
subjects:
- kind: ServiceAccount
  name: fastapi-sa
  namespace: default
roleRef:
  kind: Role
  name: fastapi-role
  apiGroup: rbac.authorization.k8s.io
```

#### 5.3 기본 ServiceAccount 비활성화

```yaml
# 모든 Namespace에서 default ServiceAccount 자동 마운트 비활성화
apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
  namespace: <namespace>
automountServiceAccountToken: false  # 토큰 자동 마운트 비활성화
```

---

### 6. Redis 비밀번호 미설정

**위치**: `ansible/roles/redis/tasks/main.yml:40-52`

**현재 상태**:
- ❌ Redis에 비밀번호 인증이 없습니다.
- ❌ 모든 Pod에서 Redis에 접근 가능합니다.

**위험도**: 🟠 **HIGH**

**설명**:
```yaml
containers:
- name: redis
  image: redis:7-alpine
  command:
  - redis-server
  - --appendonly yes
  # ❌ --requirepass 옵션이 없음
```

**권장 조치**:

```yaml
containers:
- name: redis
  image: redis:7-alpine
  command:
  - redis-server
  - --appendonly yes
  - --requirepass ${REDIS_PASSWORD}  # ✅ 비밀번호 설정
  env:
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: redis-secret
        key: password
```

```yaml
# Redis Secret 생성
apiVersion: v1
kind: Secret
metadata:
  name: redis-secret
  namespace: default
type: Opaque
stringData:
  password: <강력한_비밀번호>
```

---

## 🟡 중간 위험 (Medium)

### 7. RabbitMQ Management UI 비밀번호 약함

**위치**: `ansible/inventory/group_vars/all.yml:33`

```yaml
rabbitmq_password: "{{ lookup('env', 'RABBITMQ_PASSWORD') | default('changeme', true) }}"
```

**위험도**: 🟡 **MEDIUM**

**설명**:
- 기본 비밀번호가 `changeme`로 설정되어 있습니다.
- 환경 변수가 설정되지 않으면 약한 비밀번호가 사용됩니다.

**권장 조치**:
- ✅ 환경 변수 필수 설정
- ✅ 비밀번호 정책 강화 (최소 16자, 특수문자 포함)
- ✅ 비밀번호 로테이션 주기 설정

---

### 8. Worker 간 무제한 통신

**위치**: `terraform/modules/security-groups/main.tf:127-134`

```terraform
# Worker 간 통신 (Pod network)
ingress {
  description = "Worker to worker communication"
  from_port   = 0
  to_port     = 0
  protocol    = "-1"  # 모든 프로토콜, 모든 포트
  self        = true
}
```

**위험도**: 🟡 **MEDIUM**

**설명**:
- Worker 노드 간 모든 트래픽이 허용됩니다.
- Pod 간 통신은 Calico CNI 레벨에서 제어할 수 있으므로, AWS Security Group보다는 NetworkPolicy로 제어하는 것이 권장됩니다.

**권장 조치**:
- NetworkPolicy로 세분화된 제어 (위의 NetworkPolicy 섹션 참조)
- AWS Security Group은 최소한의 포트만 허용

---

### 9. ALB Controller 광범위한 IAM 권한

**위치**: `terraform/alb-controller-iam.tf`

**현재 상태**:
- ✅ 조건부 제한이 있음 (`aws:ResourceTag/elbv2.k8s.aws/cluster`)
- ⚠️ 하지만 여전히 많은 AWS 리소스에 접근 가능

**위험도**: 🟡 **MEDIUM**

**설명**:
- ALB Controller는 Load Balancer, Target Group, Security Group 등을 생성/수정할 수 있는 광범위한 권한이 필요합니다.
- 하지만 조건부 제한(`aws:ResourceTag`)으로 인해 클러스터 외부 리소스에는 접근이 제한됩니다.

**권장 조치**:
- ✅ 현재 설정 유지 (조건부 제한이 적절함)
- ✅ 정기적인 IAM 권한 감사
- ✅ CloudTrail을 통한 ALB Controller API 호출 모니터링

---

## ✅ 양호한 설정 (Good)

### 10. EBS CSI Driver IAM 권한

**위치**: `terraform/iam.tf:37-69`

**상태**: ✅ **GOOD**

**설명**:
- EBS 볼륨 생성을 위한 최소 필수 권한만 부여되어 있습니다.
- Resource는 `"*"`이지만, EBS 볼륨의 특성상 어쩔 수 없는 부분입니다.

---

### 11. etcd 포트 제한

**위치**: `terraform/modules/security-groups/main.tf:42-49`

**상태**: ✅ **GOOD**

```terraform
# etcd server client API
ingress {
  description = "etcd"
  from_port   = 2379
  to_port     = 2380
  protocol    = "tcp"
  self        = true  # ✅ 자기 자신에게만 허용
}
```

**설명**:
- etcd 포트는 Master 노드 자신에게만 허용되어 있습니다.

---

## 📊 요약 및 우선순위

### 즉시 조치 필요 (Critical)

1. **Kubernetes API Server 접근 제한** (포트 6443)
2. **NodePort 접근 제한** (포트 30000-32767)
3. **Master → Worker 트래픽 제한** (모든 프로토콜 → 필요한 포트만)

### 단기 조치 (1-2주)

4. **NetworkPolicy 구현** (RabbitMQ, Redis, 기본 거부 정책)
5. **RBAC 정책 구현** (ServiceAccount, Role, RoleBinding)
6. **Redis 비밀번호 설정**

### 중기 조치 (1개월)

7. **Pod Security Standards 활성화**
8. **비밀번호 정책 강화**
9. **정기적인 보안 감사 스크립트 작성**

---

## 🛠️ 구현 가이드

### 1단계: AWS Security Group 수정

```bash
# terraform/modules/security-groups/main.tf 수정
# 위의 권장 조치 적용
terraform plan
terraform apply
```

### 2단계: NetworkPolicy 적용

```bash
# NetworkPolicy 파일 생성
ansible/roles/rabbitmq/files/network-policy.yml
ansible/roles/redis/files/network-policy.yml

# Ansible playbook에 추가
ansible/roles/rabbitmq/tasks/main.yml
ansible/roles/redis/tasks/main.yml
```

### 3단계: RBAC 구현

```bash
# ServiceAccount 및 Role 생성
ansible/roles/fastapi/files/rbac.yml
ansible/roles/celery/files/rbac.yml

# Ansible playbook에 추가
```

### 4단계: Redis 비밀번호 설정

```bash
# Secret 생성
kubectl create secret generic redis-secret \
  --from-literal=password=$(openssl rand -base64 32) \
  -n default

# Redis Deployment 수정
ansible/roles/redis/tasks/main.yml
```

---

## 📚 참고 자료

- [Kubernetes NetworkPolicy 가이드](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Kubernetes RBAC 가이드](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [AWS Security Best Practices](https://aws.github.io/aws-eks-best-practices/security/docs/)

---

**작성자**: Auto (AI Assistant)  
**최종 수정**: 2025-11-03

