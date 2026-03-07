# Karpenter: Kubernetes Node Autoscaling

> **Part VIII: 인프라 스케일링** | [← 15. Distributed Tracing](./15-distributed-tracing-opentelemetry.md) | [인덱스](./00-index.md)

> 참고: [Karpenter Documentation](https://karpenter.sh/docs/)  
> 참고: [AWS Karpenter GitHub](https://github.com/aws/karpenter-provider-aws)  
> 참고: [CNCF Karpenter](https://www.cncf.io/projects/karpenter/)

---

## 들어가며

Kubernetes에서 Pod 스케일링(HPA, KEDA)은 잘 작동하지만, **노드 리소스가 부족하면 Pod는 Pending 상태**에 머문다. 기존 Cluster Autoscaler는 ASG(Auto Scaling Group)에 의존하여 스케일업이 느리고 인스턴스 타입 선택이 제한적이다.

```
┌─────────────────────────────────────────────────────────────┐
│               노드 스케일링의 필요성                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  KEDA: "RabbitMQ 큐에 100개 메시지! Pod 10개로 스케일업!"    │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  scan-worker Pod 1  ✓ Running                        │  │
│  │  scan-worker Pod 2  ✓ Running                        │  │
│  │  scan-worker Pod 3  ✓ Running                        │  │
│  │  scan-worker Pod 4  ⏳ Pending (Insufficient CPU)    │  │
│  │  scan-worker Pod 5  ⏳ Pending (Insufficient CPU)    │  │
│  │  scan-worker Pod 6  ⏳ Pending (Insufficient CPU)    │  │
│  │  ...                                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  문제: worker-ai 노드(t3.medium)가 3개 Pod만 수용 가능      │
│  해결: 노드 자동 추가 → Karpenter                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Karpenter**는 AWS에서 개발하고 CNCF에 기증한 노드 오토스케일러로, **EC2 Fleet API를 직접 호출**하여 30-60초 내에 최적의 인스턴스를 프로비저닝한다.

---

## Cluster Autoscaler vs Karpenter

```
┌─────────────────────────────────────────────────────────────┐
│            Cluster Autoscaler vs Karpenter                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Cluster Autoscaler                 Karpenter               │
│  ──────────────────                 ─────────               │
│                                                             │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │   Scheduler     │               │   Scheduler     │     │
│  │  (Pending Pod)  │               │  (Pending Pod)  │     │
│  └────────┬────────┘               └────────┬────────┘     │
│           │                                  │              │
│           ▼                                  ▼              │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │ Cluster         │               │  Karpenter      │     │
│  │ Autoscaler      │               │  Controller     │     │
│  └────────┬────────┘               └────────┬────────┘     │
│           │                                  │              │
│           ▼                                  ▼              │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │ Auto Scaling    │               │  EC2 Fleet API  │     │
│  │ Group (ASG)     │               │  (직접 호출)    │     │
│  └────────┬────────┘               └────────┬────────┘     │
│           │                                  │              │
│           ▼                                  ▼              │
│  ┌─────────────────┐               ┌─────────────────┐     │
│  │  EC2 Instance   │               │  EC2 Instance   │     │
│  │  (ASG Template) │               │  (최적 선택)    │     │
│  └─────────────────┘               └─────────────────┘     │
│                                                             │
│  스케일업 시간: 2-5분               스케일업 시간: 30-60초  │
│  인스턴스 타입: ASG에 사전 정의     인스턴스 타입: 실시간 선택│
│  Bin Packing: 제한적               Bin Packing: 최적화      │
│  Node Group 관리 필요              Node Group 불필요        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 비교 요약

| 항목 | Cluster Autoscaler | Karpenter |
|------|-------------------|-----------|
| **스케일업 시간** | 2-5분 | 30-60초 |
| **인스턴스 선택** | ASG Launch Template | 실시간 최적 선택 |
| **Bin Packing** | 제한적 | 고급 최적화 |
| **비용 최적화** | 수동 설정 | 자동 (Consolidation) |
| **Spot 지원** | ASG 설정 | 네이티브 Fallback |
| **관리 복잡도** | ASG + Node Group | NodePool CR만 |
| **CNCF 상태** | - | Graduated (2024) |

---

## Karpenter 아키텍처

### 핵심 컴포넌트

```
┌─────────────────────────────────────────────────────────────┐
│                 Karpenter 아키텍처                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Kubernetes API Server                │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                                │
│     ┌──────────────────────┼──────────────────────┐        │
│     │                      │                      │        │
│     ▼                      ▼                      ▼        │
│  ┌────────┐          ┌──────────┐          ┌──────────┐   │
│  │NodePool│          │EC2Node   │          │NodeClaim │   │
│  │  CR    │          │Class CR  │          │    CR    │   │
│  └────────┘          └──────────┘          └──────────┘   │
│     │                      │                      ▲        │
│     │  정책 정의           │  AWS 설정           │ 생성    │
│     │  (인스턴스 타입,     │  (AMI, Subnet,      │        │
│     │   limits, labels)   │   SecurityGroup)    │        │
│     │                      │                      │        │
│     └──────────────────────┼──────────────────────┘        │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Karpenter Controller                    │   │
│  │  ┌───────────────┐  ┌───────────────┐              │   │
│  │  │   Provisioner │  │   Disruption  │              │   │
│  │  │   (스케일업)  │  │   (스케일다운)│              │   │
│  │  └───────┬───────┘  └───────┬───────┘              │   │
│  │          │                  │                       │   │
│  │          └────────┬─────────┘                       │   │
│  │                   │                                  │   │
│  └───────────────────┼──────────────────────────────────┘   │
│                      │                                      │
│                      ▼                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 AWS EC2 Fleet API                    │   │
│  │  • RunInstances (최적 인스턴스 타입 선택)           │   │
│  │  • TerminateInstances (노드 제거)                   │   │
│  │  • DescribeInstances (상태 모니터링)                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 프로비저닝 흐름

```
┌─────────────────────────────────────────────────────────────┐
│              Karpenter 프로비저닝 흐름                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Pending Pod 감지                                        │
│  ─────────────────────                                      │
│  Scheduler: "이 Pod를 스케줄할 노드가 없음"                 │
│  Karpenter: (Watch) "Pending Pod 발견!"                     │
│                                                             │
│  2. NodeClaim 생성                                          │
│  ──────────────────                                         │
│  Karpenter → NodeClaim CR 생성                              │
│  • Pending Pod들의 리소스 요구사항 집계                     │
│  • NodePool 정책에 따른 제약 조건 적용                      │
│                                                             │
│  3. 인스턴스 타입 선택                                      │
│  ─────────────────────                                      │
│  Karpenter:                                                 │
│  • 가격, 가용성, 리소스 fit 고려                           │
│  • Bin Packing: 최소 비용으로 최대 Pod 수용                │
│  • 예: 4 vCPU 필요 → t3.medium × 2 vs t3.xlarge × 1        │
│                                                             │
│  4. EC2 인스턴스 생성                                       │
│  ─────────────────────                                      │
│  EC2 Fleet API:                                             │
│  • RunInstances 호출                                        │
│  • userData로 kubelet 부트스트랩                            │
│  • 30-60초 내 노드 Ready                                   │
│                                                             │
│  5. Pod 스케줄링                                            │
│  ────────────────                                           │
│  Scheduler: 새 노드에 Pending Pod 스케줄                    │
│  Pod: Running 상태로 전환                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## CRD 분석

### 1. NodePool (정책 정의)

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: worker-scalable
spec:
  # 노드 템플릿
  template:
    metadata:
      labels:
        role: worker
        managed-by: karpenter
    spec:
      # EC2NodeClass 참조
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      
      # 인스턴스 요구사항
      requirements:
      # 인스턴스 타입 제한
      - key: "node.kubernetes.io/instance-type"
        operator: In
        values: ["t3.medium", "t3.large", "t3.xlarge"]
      
      # On-Demand vs Spot
      - key: "karpenter.sh/capacity-type"
        operator: In
        values: ["on-demand"]  # 또는 ["spot", "on-demand"]
      
      # 아키텍처
      - key: "kubernetes.io/arch"
        operator: In
        values: ["amd64"]
      
      # Availability Zone
      - key: "topology.kubernetes.io/zone"
        operator: In
        values: ["ap-northeast-2a", "ap-northeast-2c"]
      
      # Taints (선택적)
      taints:
      - key: "workload"
        value: "ai"
        effect: "NoSchedule"
  
  # 리소스 한도 (vCPU Quota 초과 방지)
  limits:
    cpu: 20       # 최대 20 vCPU
    memory: 40Gi  # 최대 40GB 메모리
  
  # 노드 축소 정책
  disruption:
    # WhenEmpty: 노드가 비면 즉시 제거
    # WhenEmptyOrUnderutilized: 비거나 활용도 낮으면 제거
    consolidationPolicy: WhenEmpty
    consolidateAfter: 30s
    
    # 예산: 동시에 중단할 수 있는 노드 수
    budgets:
    - nodes: "10%"    # 전체의 10%까지
    - nodes: "1"      # 또는 최소 1개
```

### 2. EC2NodeClass (AWS 설정)

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  # AMI 선택
  amiFamily: Ubuntu  # AL2023, Bottlerocket, Ubuntu
  
  # 또는 특정 AMI 지정
  # amiSelectorTerms:
  # - id: ami-0123456789abcdef0
  
  # IAM Instance Profile
  instanceProfile: karpenter-node-profile
  
  # 네트워크 설정
  subnetSelectorTerms:
  - tags:
      karpenter.sh/discovery: "true"
  
  securityGroupSelectorTerms:
  - tags:
      karpenter.sh/discovery: "true"
  
  # 블록 디바이스
  blockDeviceMappings:
  - deviceName: /dev/sda1
    ebs:
      volumeSize: 40Gi
      volumeType: gp3
      encrypted: true
  
  # 메타데이터 옵션
  metadataOptions:
    httpEndpoint: enabled
    httpProtocolIPv6: disabled
    httpPutResponseHopLimit: 2
    httpTokens: required  # IMDSv2 필수
  
  # 사용자 데이터 (kubeadm join 등)
  userData: |
    #!/bin/bash
    set -ex
    
    # Kubernetes 패키지 설치
    apt-get update
    apt-get install -y containerd kubelet kubeadm kubectl
    
    # containerd 설정
    containerd config default > /etc/containerd/config.toml
    systemctl restart containerd
    
    # kubeadm join 실행
    kubeadm join ${CLUSTER_ENDPOINT}:6443 \
      --token ${BOOTSTRAP_TOKEN} \
      --discovery-token-ca-cert-hash sha256:${CA_CERT_HASH}
  
  # 태그
  tags:
    Environment: dev
    ManagedBy: karpenter
```

### 3. NodeClaim (자동 생성됨)

```yaml
# Karpenter가 자동 생성하는 CR - 직접 생성하지 않음
apiVersion: karpenter.sh/v1
kind: NodeClaim
metadata:
  name: worker-scalable-abc123
  ownerReferences:
  - apiVersion: karpenter.sh/v1
    kind: NodePool
    name: worker-scalable
spec:
  nodeClassRef:
    group: karpenter.k8s.aws
    kind: EC2NodeClass
    name: default
  requirements:
  - key: "node.kubernetes.io/instance-type"
    operator: In
    values: ["t3.large"]
status:
  # 인스턴스 정보
  providerID: aws:///ap-northeast-2a/i-0abc123def456
  nodeName: ip-10-0-1-123.ap-northeast-2.compute.internal
  capacity:
    cpu: "2"
    memory: 8Gi
  conditions:
  - type: Registered
    status: "True"
  - type: Initialized
    status: "True"
  - type: Ready
    status: "True"
```

---

## AWS IAM 권한

### Karpenter Controller 권한

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EC2NodeProvisioning",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:CreateFleet",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceTypes",
        "ec2:DescribeInstanceTypeOfferings",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeLaunchTemplates",
        "ec2:DescribeImages",
        "ec2:DescribeSpotPriceHistory"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2TagManagement",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "ec2:DeleteTags"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ec2:CreateAction": ["RunInstances", "CreateFleet"]
        }
      }
    },
    {
      "Sid": "IAMPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/KarpenterNodeRole-*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ec2.amazonaws.com"
        }
      }
    },
    {
      "Sid": "SSMGetParameter",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:*:*:parameter/aws/service/*"
    },
    {
      "Sid": "PricingAPI",
      "Effect": "Allow",
      "Action": "pricing:GetProducts",
      "Resource": "*"
    },
    {
      "Sid": "SQSInterruption",
      "Effect": "Allow",
      "Action": [
        "sqs:DeleteMessage",
        "sqs:GetQueueUrl",
        "sqs:ReceiveMessage"
      ],
      "Resource": "arn:aws:sqs:*:*:Karpenter-*"
    }
  ]
}
```

### Node Instance Profile 권한

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Disruption (노드 축소)

### Consolidation 정책

```
┌─────────────────────────────────────────────────────────────┐
│                 Karpenter Consolidation                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WhenEmpty (기본)                                           │
│  ───────────────                                            │
│  노드에 Pod가 하나도 없으면 즉시 제거                       │
│                                                             │
│  [Node A]        [Node B]        [Node C]                  │
│  Pod1 Pod2       (empty)         Pod3                       │
│     ✓              ✗ 제거          ✓                        │
│                                                             │
│  WhenEmptyOrUnderutilized                                   │
│  ─────────────────────────                                  │
│  비어있거나 활용도가 낮으면 재배치 후 제거                  │
│                                                             │
│  Before:                                                    │
│  [Node A: 20%]   [Node B: 30%]   [Node C: 10%]             │
│                                                             │
│  After Consolidation:                                       │
│  [Node A: 60%]   (terminated)    (terminated)              │
│  Pod들이 Node A로 재배치됨                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Disruption Budgets

```yaml
spec:
  disruption:
    budgets:
    # 언제나 최소 90%는 유지
    - nodes: "10%"
    
    # 업무 시간에는 중단 금지
    - nodes: "0"
      schedule: "0 9-17 * * mon-fri"  # 평일 9-17시
      duration: 8h
    
    # 주말에는 자유롭게 통합
    - nodes: "100%"
      schedule: "0 0 * * sat,sun"
      duration: 48h
```

---

## Bin Packing 최적화

```
┌─────────────────────────────────────────────────────────────┐
│                 Karpenter Bin Packing                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시나리오: 5개 Pod 필요 (각 1 vCPU, 2GB)                    │
│                                                             │
│  Cluster Autoscaler (ASG: t3.medium 고정)                  │
│  ───────────────────────────────────────                    │
│  t3.medium (2 vCPU, 4GB) × 3 = 6 vCPU, 12GB                │
│  비용: $0.0416 × 3 = $0.1248/hr                            │
│                                                             │
│  [Node 1]        [Node 2]        [Node 3]                  │
│  Pod1 Pod2       Pod3 Pod4       Pod5 (빈 공간)            │
│                                                             │
│  Karpenter (최적 선택)                                      │
│  ────────────────────                                       │
│  t3.xlarge (4 vCPU, 16GB) × 1 + t3.small (2 vCPU, 2GB) × 1 │
│  또는                                                       │
│  t3.large (2 vCPU, 8GB) × 2 + t3.micro × 1                 │
│                                                             │
│  실시간으로 가격, 가용성, fit을 계산하여 최적 조합 선택     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## KEDA + Karpenter 통합

```
┌─────────────────────────────────────────────────────────────┐
│               KEDA + Karpenter 통합 아키텍처                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ Queue Length: 100                                 │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │    KEDA      │ ScaledObject: scan-worker                │
│  │  ScaledObject│ threshold: 10 messages/pod               │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │     HPA      │ desiredReplicas: 10                      │
│  │ (KEDA 생성)  │ currentReplicas: 3                       │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Scheduler   │ 7개 Pod → Pending (리소스 부족)          │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Karpenter   │ Pending Pod 감지                         │
│  │  Controller  │ NodeClaim 생성                           │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │ EC2 Fleet    │ t3.large × 2 프로비저닝                  │
│  │    API       │ 30-60초 내 Ready                         │
│  └──────┬───────┘                                          │
│         │                                                   │
│         ▼                                                   │
│  ┌──────────────┐                                          │
│  │  Scheduler   │ 7개 Pending Pod → Running                │
│  └──────────────┘                                          │
│                                                             │
│  Queue 비면:                                                │
│  KEDA → HPA → Pod 수 감소 → Node 빔 → Karpenter 제거       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## kubeadm 클러스터 호환성

### EKS vs kubeadm

| 항목 | EKS | kubeadm |
|------|-----|---------|
| **노드 부트스트랩** | EKS Managed | userData 직접 작성 |
| **인증** | aws-iam-authenticator | Bootstrap Token |
| **AMI** | EKS Optimized AMI | Ubuntu/직접 준비 |
| **CNI** | VPC CNI | Calico/Flannel/Cilium |
| **userData** | 간단 | 복잡 (kubeadm join) |

### kubeadm용 userData 템플릿

```bash
#!/bin/bash
set -ex

# 변수 설정 (Karpenter가 주입)
CLUSTER_ENDPOINT="${CLUSTER_ENDPOINT}"
BOOTSTRAP_TOKEN="${BOOTSTRAP_TOKEN}"
CA_CERT_HASH="${CA_CERT_HASH}"

# 1. OS 설정
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# 커널 모듈
cat <<EOF | tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter

# sysctl
cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

# 2. containerd 설치
apt-get update
apt-get install -y containerd
mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
systemctl restart containerd

# 3. Kubernetes 패키지 설치
apt-get install -y apt-transport-https ca-certificates curl
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | \
  gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /' | \
  tee /etc/apt/sources.list.d/kubernetes.list
apt-get update
apt-get install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

# 4. kubeadm join
kubeadm join ${CLUSTER_ENDPOINT}:6443 \
  --token ${BOOTSTRAP_TOKEN} \
  --discovery-token-ca-cert-hash sha256:${CA_CERT_HASH}
```

### Bootstrap Token 관리

```
┌─────────────────────────────────────────────────────────────┐
│             Bootstrap Token 관리 전략                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  문제: Bootstrap Token은 기본 24시간 후 만료                │
│                                                             │
│  해결 방안:                                                 │
│                                                             │
│  1. Long-lived Token (비권장)                               │
│     kubeadm token create --ttl 0                           │
│     보안 위험, 운영 환경에서 사용 금지                      │
│                                                             │
│  2. Token 자동 갱신 CronJob                                 │
│     - CronJob이 주기적으로 새 Token 생성                    │
│     - AWS SSM Parameter Store에 저장                        │
│     - EC2NodeClass userData가 SSM에서 조회                  │
│                                                             │
│  3. Node Authorizer (권장)                                  │
│     - Bootstrap Token 대신 Node Authorizer 사용            │
│     - kubelet TLS bootstrapping                            │
│     - 노드가 CSR 자동 승인                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 모니터링

### Prometheus 메트릭

```
# Karpenter 메트릭

# 노드 프로비저닝
karpenter_nodes_created_total{nodepool, provisioner}
karpenter_nodes_terminated_total{nodepool, reason}
karpenter_provisioner_scheduling_duration_seconds{nodepool}

# 비용
karpenter_nodes_total_pod_requests{resource_type, nodepool}
karpenter_nodes_total_pod_limits{resource_type, nodepool}
karpenter_nodes_allocatable{resource_type, nodepool}

# Disruption
karpenter_disruption_actions_performed_total{action, nodepool}
karpenter_disruption_pods_disrupted_total{nodepool}

# 예시 쿼리
# 현재 Karpenter가 관리하는 노드 수
count(karpenter_nodes_created_total) - count(karpenter_nodes_terminated_total)

# 프로비저닝 latency p99
histogram_quantile(0.99, karpenter_provisioner_scheduling_duration_seconds_bucket)
```

### 대시보드 패널

```
┌─────────────────────────────────────────────────────────────┐
│                 Karpenter Dashboard                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Active Nodes     │  │ Pending Pods     │                │
│  │      5           │  │       0          │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ CPU Utilization  │  │ Memory Util      │                │
│  │     65%          │  │      48%         │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Node Provisioning Timeline                          │   │
│  │ ─────────────────────────────────────────────────── │   │
│  │ 10:00  +2 nodes (t3.large)                         │   │
│  │ 10:30  -1 node (consolidation)                     │   │
│  │ 11:00  +1 node (t3.medium)                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Instance Type Distribution                          │   │
│  │ [████████████ t3.medium (3)  ████████ t3.large (2)] │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Eco² 적용

### 현재 상태

```
┌─────────────────────────────────────────────────────────────┐
│               Eco² 현재 노드 구성 (Terraform)                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  고정 노드 (17개):                                          │
│  ─────────────────                                          │
│                                                             │
│  Control Plane:                                             │
│  • k8s-master (t3.xlarge)                                  │
│                                                             │
│  API Nodes (Taint: domain=xxx:NoSchedule):                 │
│  • k8s-api-auth, my, scan, character, location (t3.small)  │
│  • k8s-api-image, chat (t3.medium)                         │
│                                                             │
│  Worker Nodes:                                              │
│  • k8s-worker-ai (t3.medium) ← 스케일 필요!                │
│  • k8s-worker-storage (t3.medium)                          │
│                                                             │
│  Infrastructure (Taint: domain=xxx:NoSchedule):            │
│  • k8s-postgresql, redis-*, rabbitmq, monitoring, logging  │
│                                                             │
│  Network:                                                   │
│  • k8s-ingress-gateway (t3.medium)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Karpenter 도입 후

```
┌─────────────────────────────────────────────────────────────┐
│               Eco² Karpenter 도입 후                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Terraform (Base Capacity) - 고정                           │
│  ────────────────────────────────                           │
│  • 모든 Infrastructure 노드 (변경 없음)                     │
│  • Control Plane (변경 없음)                                │
│  • k8s-worker-ai (Base 1개)                                │
│  • k8s-worker-storage (Base 1개)                           │
│                                                             │
│  Karpenter (Scale Out) - 동적                               │
│  ─────────────────────────────                              │
│  • worker-ai-xxx (KEDA가 Pod 늘리면 자동 생성)              │
│  • worker-storage-yyy (필요 시 자동 생성)                   │
│  • api-scan-zzz (API 부하 증가 시)                          │
│                                                             │
│  NodePool 설정:                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ NodePool: worker-scalable                             │ │
│  │ • instance-types: t3.medium, t3.large                 │ │
│  │ • capacity-type: on-demand                            │ │
│  │ • limits: 20 vCPU, 40Gi memory                        │ │
│  │ • consolidation: WhenEmpty, 30s                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## References

### 공식 문서

- [Karpenter Documentation](https://karpenter.sh/docs/)
- [Karpenter GitHub](https://github.com/aws/karpenter-provider-aws)
- [Karpenter Best Practices](https://aws.github.io/aws-eks-best-practices/karpenter/)

### AWS 블로그

- [Introducing Karpenter](https://aws.amazon.com/blogs/aws/introducing-karpenter-an-open-source-high-performance-kubernetes-cluster-autoscaler/)
- [Karpenter vs Cluster Autoscaler](https://aws.amazon.com/blogs/containers/comparing-cluster-autoscaler-and-karpenter/)

### CNCF

- [Karpenter Graduation Announcement](https://www.cncf.io/announcements/2024/12/09/cloud-native-computing-foundation-announces-karpenter-graduation/)

---

## 버전 정보

| 항목 | 버전 |
|------|------|
| 작성일 | 2025-12-26 |
| Karpenter | 1.1.0 |
| Kubernetes | 1.28+ |
| AWS Provider | aws/karpenter-provider-aws |

