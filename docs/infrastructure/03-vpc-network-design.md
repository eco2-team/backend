# 🌐 VPC 네트워크 설계

> **4-Tier Kubernetes 클러스터용 네트워크 구성**  
> **날짜**: 2025-10-31

## 📋 목차

1. [VPC 개요](#vpc-개요)
2. [Subnets 설계](#subnets-설계)
3. [Security Groups](#security-groups)
4. [라우팅 테이블](#라우팅-테이블)
5. [네트워크 흐름](#네트워크-흐름)

---

## 🏗️ VPC 개요

### 기본 정보

```
VPC CIDR: 10.0.0.0/16
Region: ap-northeast-2 (Seoul)
Availability Zones: 3개 (a, b, c)
DNS Hostnames: Enabled
DNS Support: Enabled

사용 가능 IP: 65,536개
실제 사용: ~500개
여유: 충분 ✅
```

### VPC Tags

```yaml
Name: prod-k8s-vpc
Project: SeSACTHON
ManagedBy: Terraform
kubernetes.io/cluster/prod-sesacthon: shared
```

**kubernetes.io/cluster 태그**: ALB Controller가 VPC 자동 인식

---

## 🗺️ Subnets 설계

### 3개 Public Subnets (Private 없음)

```mermaid
graph TB
    subgraph VPC["VPC (10.0.0.0/16)"]
        subgraph Subnet1["Subnet 1 (10.0.1.0/24) - ap-northeast-2a"]
            Master["Master<br/>10.0.1.235<br/>EIP: 52.78"]
            Storage["Storage<br/>10.0.1.x"]
            S1Info["• 256 IPs<br/>• Public ✅<br/>• kubernetes.io/role/elb=1"]
        end
        
        subgraph Subnet2["Subnet 2 (10.0.2.0/24) - ap-northeast-2b"]
            Worker1["Worker-1<br/>10.0.2.x<br/>App Pods"]
            S2Info["• 256 IPs<br/>• Public ✅"]
        end
        
        subgraph Subnet3["Subnet 3 (10.0.3.0/24) - ap-northeast-2c"]
            Worker2["Worker-2<br/>10.0.3.x<br/>Celery"]
            S3Info["• 256 IPs<br/>• Public ✅"]
        end
    end
    
    style VPC fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    style Subnet1 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style Subnet2 fill:#f1f8e9,stroke:#33691e,stroke-width:2px
    style Subnet3 fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    style Master fill:#ffccbc,stroke:#bf360c,stroke-width:2px
    style Storage fill:#ffccbc,stroke:#bf360c,stroke-width:2px
    style Worker1 fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px
    style Worker2 fill:#f8bbd0,stroke:#880e4f,stroke-width:2px
```

### 왜 Public Subnet만?

```
장점:
✅ NAT Gateway 불필요 ($96/월 절감)
✅ 직접 인터넷 접속 (빠름)
✅ 관리 단순

보안:
✅ Security Group으로 제어
✅ 필요한 포트만 개방
✅ Pod IP는 Private (192.168.x.x)

적합:
- 소규모 클러스터 (4 nodes)
- MVP, 개발 환경
- 비용 최적화
```

---

## 🔒 Security Groups

### Master Security Group

```yaml
Name: prod-k8s-master-sg
Applies to: Master 노드만

Inbound Rules:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internet Access
- SSH (22/TCP):           YOUR_IP → Master
- K8s API (6443/TCP):     0.0.0.0/0 → Master
- HTTP (80/TCP):          0.0.0.0/0 → Master (리디렉션)
- HTTPS (443/TCP):        0.0.0.0/0 → Master
- NodePort (30000-32767): 0.0.0.0/0 → Master

# Control Plane (Self)
- etcd (2379-2380/TCP):         Master → Master
- Kubelet (10250/TCP):          Master → Master
- Scheduler (10259/TCP):        Master → Master
- Controller-Mgr (10257/TCP):   Master → Master
- VXLAN (4789/UDP):             Master → Master

# From Workers
- K8s API (6443/TCP):      Worker SG → Master
- Kubelet (10250-10252):   Worker SG → Master
- VXLAN (4789/UDP):        Worker SG → Master

Outbound:
- All traffic to 0.0.0.0/0
```

### Worker Security Group

```yaml
Name: prod-k8s-worker-sg
Applies to: Worker-1, Worker-2, Storage

Inbound Rules:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internet Access
- SSH (22/TCP):       YOUR_IP → Worker

# Worker 간 통신 (Self)
- All traffic:        Worker → Worker
- VXLAN (4789/UDP):   Worker → Worker
- kube-proxy (10256): Worker → Worker

# From Master
- Kubelet (10250/TCP):      Master SG → Worker
- NodePort (30000-32767):   Master SG → Worker
- All traffic:              Master SG → Worker
- VXLAN (4789/UDP):         Master SG → Worker

Outbound:
- All traffic to 0.0.0.0/0
```

---

## 🔄 라우팅 테이블

### Public Route Table

```
Name: prod-public-rt
Associated Subnets: Subnet 1, 2, 3 (모두)

Routes:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Destination         Target              설명
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
10.0.0.0/16        local               VPC 내부 통신
0.0.0.0/0          igw-xxx             인터넷 (양방향)

Pod CIDR (Calico):
192.168.0.0/16     Worker ENIs         Pod 통신
  ├─ 192.168.0.0/24   → Master
  ├─ 192.168.1.0/24   → Storage
  ├─ 192.168.2.0/24   → Worker-1
  └─ 192.168.x.x/24   → Worker-2

Note: Pod CIDR은 Calico가 관리, VPC Route 불필요
      (VXLAN Overlay)
```

---

## 🌐 네트워크 흐름

### 외부 → Master (Kubernetes API)

```mermaid
graph TD
    User["사용자 (인터넷)"] -->|"HTTPS:6443"| IGW["Internet Gateway"]
    IGW -->|"NAT (EIP → 10.0.1.235)"| VPC["VPC (10.0.0.0/16)"]
    VPC -->|"Route Table<br/>(10.0.1.235 → Subnet 1)"| ENI["Master ENI<br/>(10.0.1.235)"]
    ENI -->|"Security Group<br/>(6443 허용)"| API["kube-apiserver:6443"]
    
    style User fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style IGW fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style VPC fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style ENI fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style API fill:#fce4ec,stroke:#c2185b,stroke-width:2px
```

### ALB → Pod (Application Traffic)

```mermaid
graph TD
    Browser["브라우저"] -->|"HTTPS"| IGW["Internet Gateway"]
    IGW -->|"NAT"| ALB["ALB (Public Subnets 1,2,3)<br/>- TLS 종료 (ACM)<br/>- Path: /api/v1/auth"]
    ALB -->|"HTTP (평문)"| Route["VPC Routing<br/>(192.168.x.x → Worker ENI)"]
    Route --> ENI["Worker-1 ENI<br/>(10.0.2.x)"]
    ENI -->|"Calico VXLAN"| Pod["Pod<br/>(192.168.2.x)"]
    Pod --> Service["auth-service:8000"]
    
    style Browser fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style IGW fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style ALB fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    style Route fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style ENI fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Pod fill:#e1bee7,stroke:#7b1fa2,stroke-width:2px
    style Service fill:#fce4ec,stroke:#c2185b,stroke-width:2px
```

### Pod → S3 (이미지 다운로드)

```mermaid
graph TD
    Pod["Celery Worker Pod<br/>(192.168.x.x)"] -->|"HTTPS"| Calico["Calico → Worker ENI"]
    Calico --> Route["VPC Route<br/>(0.0.0.0/0 → IGW)"]
    Route --> IGW["Internet Gateway"]
    IGW --> S3E["S3 Endpoint<br/>(VPC Endpoint 권장)"]
    S3E --> Bucket["prod-sesacthon-images<br/>bucket"]
    
    style Pod fill:#e1bee7,stroke:#7b1fa2,stroke-width:2px
    style Calico fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style Route fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style IGW fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style S3E fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    style Bucket fill:#fce4ec,stroke:#c2185b,stroke-width:2px
```

---

## 🔐 보안 계층

```mermaid
graph TB
    subgraph Layer1["계층 1: VPC Isolation"]
        VPC1["논리적 네트워크 분리"]
        VPC2["10.0.0.0/16만 사용"]
    end
    
    subgraph Layer2["계층 2: Security Groups (Stateful Firewall)"]
        SG1["Master SG: Control Plane 포트만"]
        SG2["Worker SG: Pod 통신 포트만"]
        SG3["Cross-SG rules: 최소 권한"]
    end
    
    subgraph Layer3["계층 3: Network Policies (Kubernetes)"]
        NP1["Calico NetworkPolicy (선택)"]
        NP2["Pod 간 통신 제어"]
    end
    
    subgraph Layer4["계층 4: IAM (리소스 권한)"]
        IAM1["Instance Profile"]
        IAM2["S3 Pre-signed URL"]
        IAM3["ALB Controller 권한"]
    end
    
    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> Layer4
    
    style Layer1 fill:#e3f2fd,stroke:#1565c0,stroke-width:3px
    style Layer2 fill:#fff3e0,stroke:#e65100,stroke-width:3px
    style Layer3 fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style Layer4 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:3px
```

---

## 💰 비용 최적화

```
Public Subnet만 사용:
- NAT Gateway 없음: -$96/월
- 데이터 전송 무료 (IGW)
- 총 절감: $96/월

대신:
✅ Security Group으로 보안
✅ 적은 노드 수 (4개)
✅ Pod IP는 Private 유지
```

---

## 📚 참고 문서

- [AWS VPC Best Practices](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html)
- [Kubernetes Networking](https://kubernetes.io/docs/concepts/cluster-administration/networking/)
- [Calico VXLAN](https://docs.tigera.io/calico/latest/networking/configuring/vxlan-ipip)

---

**작성일**: 2025-10-31  
**버전**: 2.0 (4-Tier cluster)

