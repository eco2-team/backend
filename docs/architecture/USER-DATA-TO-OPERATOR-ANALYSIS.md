# User-Data 기능을 대체할 수 있는 Operator 분석

## 📋 목차

1. [현재 User-Data가 하는 일](#현재-user-data가-하는-일)
2. [Operator 대체 가능성 분석](#operator-대체-가능성-분석)
3. [추천 솔루션](#추천-솔루션)
4. [결론 및 권장사항](#결론-및-권장사항)

---

## 현재 User-Data가 하는 일

### Master Node (master-combined.sh)
```bash
1. OS 설정
   - swap 비활성화
   - 커널 모듈 로드 (overlay, br_netfilter)
   - sysctl 네트워크 설정
   - CNI 디렉토리 생성

2. Container Runtime 설치
   - Docker 설치
   - containerd 설정 (SystemdCgroup, CRI 활성화)
   
3. Kubernetes 패키지 설치
   - kubelet, kubeadm, kubectl 설치 (v1.28)
   
4. 클러스터 초기화
   - kubeadm init
   - CNI 설치 (Calico)
   - ArgoCD 설치
   
5. SSM Parameter Store
   - Join token 저장
   - API endpoint 저장
   - CA cert hash 저장
```

### Worker Node (worker-combined.sh)
```bash
1. OS 설정 (Master와 동일)
2. Container Runtime 설치 (Master와 동일)
3. Kubernetes 패키지 설치 (Master와 동일)
4. Provider ID 설정
   - AWS 메타데이터에서 정보 수집
   - kubelet에 Provider ID 설정
5. 클러스터 Join
   - SSM에서 join token 가져오기
   - kubeadm join 실행
6. Join 상태 보고
   - SSM에 상태 저장
```

---

## Operator 대체 가능성 분석

### 1. ❌ OS 설정 (Operator로 대체 **불가능**)

**현재 방식:**
- user-data에서 swap 비활성화, 커널 모듈 로드, sysctl 설정

**Operator 대체 가능성:**
- **불가능** - OS 레벨 설정은 Kubernetes가 실행되기 전에 필요함
- Operator는 Kubernetes가 실행된 후에만 작동 가능

**대안:**
1. **user-data 유지** (현재 방식)
2. **Packer + AMI**: 미리 구성된 AMI 사용
3. **cloud-init**: cloud-init 스크립트 사용
4. **Talos Linux**: Immutable OS (Kubernetes 전용 OS)

### 2. ❌ Container Runtime 설치 (Operator로 대체 **불가능**)

**현재 방식:**
- user-data에서 Docker, containerd 설치 및 설정

**Operator 대체 가능성:**
- **불가능** - Container runtime은 Kubernetes보다 먼저 설치되어야 함
- Operator를 실행할 수 없는 chicken-and-egg 문제

**대안:**
1. **user-data 유지** (현재 방식)
2. **Packer + AMI**: 미리 설치된 AMI 사용
3. **Talos Linux**: containerd가 내장된 OS

### 3. ❌ Kubernetes 패키지 설치 (Operator로 대체 **불가능**)

**현재 방식:**
- user-data에서 kubelet, kubeadm, kubectl 설치

**Operator 대체 가능성:**
- **불가능** - kubelet이 없으면 Kubernetes 노드가 될 수 없음

**대안:**
1. **user-data 유지** (현재 방식)
2. **Packer + AMI**: 미리 설치된 AMI 사용

### 4. ⚠️ 클러스터 초기화 (kubeadm init/join) - **부분적 대체 가능**

**현재 방식:**
- Master: user-data에서 `kubeadm init` 실행
- Worker: user-data에서 `kubeadm join` 실행

**Operator 대체 가능성:**
- **Cluster API (CAPI)**: ✅ 완전 대체 가능
  - **Cluster API Provider AWS (CAPA)**: AWS EC2 인스턴스를 Kubernetes 리소스로 관리
  - **kubeadm Bootstrap Provider**: kubeadm을 사용한 노드 부트스트랩 자동화
  - **MachineDeployment**: 워커 노드 수를 선언적으로 관리
  
**Cluster API 구조:**
```yaml
# Cluster API를 사용하면 아래와 같이 선언적으로 클러스터 관리
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
metadata:
  name: my-cluster
spec:
  infrastructureRef:
    apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
    kind: AWSCluster
  controlPlaneRef:
    apiVersion: controlplane.cluster.x-k8s.io/v1beta1
    kind: KubeadmControlPlane

---
apiVersion: controlplane.cluster.x-k8s.io/v1beta1
kind: KubeadmControlPlane
metadata:
  name: my-cluster-control-plane
spec:
  replicas: 3
  version: v1.28.0
  kubeadmConfigSpec:
    # kubeadm init 설정
    initConfiguration:
      nodeRegistration:
        kubeletExtraArgs:
          cloud-provider: external

---
apiVersion: cluster.x-k8s.io/v1beta1
kind: MachineDeployment
metadata:
  name: my-cluster-workers
spec:
  replicas: 10
  template:
    spec:
      bootstrap:
        configRef:
          apiVersion: bootstrap.cluster.x-k8s.io/v1beta1
          kind: KubeadmConfigTemplate
      infrastructureRef:
        apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
        kind: AWSMachineTemplate
```

**Cluster API 장점:**
- ✅ 선언적 클러스터 관리 (GitOps 친화적)
- ✅ 자동 노드 프로비저닝 및 스케일링
- ✅ Self-healing (노드 장애 시 자동 복구)
- ✅ 멀티 클러스터 관리 가능
- ✅ Rolling update 지원

**Cluster API 단점:**
- ❌ **복잡도 증가**: 학습 곡선이 가파름
- ❌ **Management Cluster 필요**: 별도의 관리 클러스터 필요
- ❌ **Overhead**: CAPI 컴포넌트 추가 설치 필요
- ❌ **Single Cluster에는 과한 구성**: 현재 프로젝트는 단일 클러스터

### 5. ✅ Provider ID 설정 (Operator로 **대체 가능**)

**현재 방식:**
- user-data에서 AWS 메타데이터 조회 후 kubelet에 Provider ID 설정

**Operator 대체 가능성:**
- **완전 대체 가능** - 이미 Custom Operator 설계 완료
- `k8s/operators/node-lifecycle/` 에 CRD, Deployment, RBAC 정의됨

**Custom Node Lifecycle Operator:**
```yaml
apiVersion: nodelifecycle.sesacthon.io/v1alpha1
kind: NodeConfig
metadata:
  name: k8s-api-auth
spec:
  nodeName: k8s-api-auth
  labels:
    service: api-auth
    tier: application
  taints:
    - key: "service"
      value: "api-auth"
      effect: "NoSchedule"
  providerID: "aws:///ap-northeast-2a/i-1234567890abcdef0"
```

**Operator 역할:**
- Node가 Ready 상태가 되면 자동으로:
  1. Provider ID 설정
  2. Node Labels 적용
  3. Node Taints 적용

### 6. ✅ ArgoCD 설치 (Operator로 **대체 가능**)

**현재 방식:**
- user-data에서 ArgoCD Helm chart 설치

**Operator 대체 가능성:**
- **ArgoCD Operator**: ✅ 완전 대체 가능
  - OperatorHub.io에서 제공
  - Red Hat에서 유지보수
  
**ArgoCD Operator 사용:**
```yaml
apiVersion: argoproj.io/v1alpha1
kind: ArgoCD
metadata:
  name: argocd
  namespace: argocd
spec:
  server:
    route:
      enabled: true
  rbac:
    policy: |
      g, system:cluster-admins, role:admin
```

---

## 추천 솔루션

### 🎯 시나리오 A: 현재 방식 유지 + Operator 추가 (단기 권장)

**장점:**
- ✅ 빠른 구현 가능
- ✅ 복잡도 낮음
- ✅ 검증된 방식

**구성:**
```
Terraform
├── EC2 인스턴스 프로비저닝
├── User-Data (압축하여 16KB 제한 해결)
│   ├── OS 설정
│   ├── Container Runtime 설치
│   ├── Kubernetes 패키지 설치
│   ├── kubeadm init/join
│   └── SSM Parameter Store 활용
└── Kubernetes Operator 배포
    ├── Node Lifecycle Operator (Labels, Taints, Provider ID)
    └── ArgoCD Operator
```

**User-Data 16KB 제한 해결 방법:**

1. **방법 1: S3에 스크립트 업로드**
```bash
# user-data.sh (간소화)
#!/bin/bash
aws s3 cp s3://my-bucket/scripts/k8s-bootstrap.sh /tmp/
chmod +x /tmp/k8s-bootstrap.sh
/tmp/k8s-bootstrap.sh
```

2. **방법 2: gzip 압축**
```terraform
data "template_cloudinit_config" "master" {
  gzip          = true
  base64_encode = true

  part {
    content_type = "text/x-shellscript"
    content      = file("${path.module}/user-data/master-combined.sh")
  }
}

resource "aws_instance" "master" {
  user_data = data.template_cloudinit_config.master.rendered
}
```

3. **방법 3: 모듈화된 스크립트**
```bash
# user-data-master.sh
#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/.../k8s-common.sh | bash
curl -fsSL https://raw.githubusercontent.com/.../master-init.sh | bash
```

### 🔄 시나리오 B: Cluster API 전환 (중장기 권장)

**장점:**
- ✅ 완전한 선언적 관리
- ✅ GitOps 친화적
- ✅ 멀티 클러스터 확장 가능
- ✅ Self-healing

**단점:**
- ❌ 학습 곡선 가파름
- ❌ Management Cluster 필요
- ❌ 복잡도 증가

**구성:**
```
Management Cluster (별도 클러스터)
├── Cluster API Controller
├── CAPA (Cluster API Provider AWS)
└── Kubeadm Bootstrap Provider

Workload Cluster (자동 생성/관리)
├── Cluster Resource (선언적 정의)
├── KubeadmControlPlane (Master 노드)
└── MachineDeployment (Worker 노드)
```

**마이그레이션 계획:**
1. **Phase 1**: 별도 Management Cluster 구축
2. **Phase 2**: Cluster API 컴포넌트 설치
3. **Phase 3**: 현재 클러스터를 Cluster API로 Import
4. **Phase 4**: Terraform → Cluster API로 전환

### 🚀 시나리오 C: Talos Linux (장기 권장)

**Talos Linux란?**
- Kubernetes 전용 Immutable OS
- API로만 관리 (SSH 불필요)
- Minimal Attack Surface

**장점:**
- ✅ OS 설정 불필요 (모두 내장)
- ✅ containerd 내장
- ✅ 보안성 향상
- ✅ 선언적 설정

**단점:**
- ❌ 새로운 OS 학습 필요
- ❌ 기존 인프라 전면 재구축
- ❌ Ubuntu/Debian 도구 사용 불가

---

## 결론 및 권장사항

### 🎯 현재 프로젝트에 맞는 선택

#### 1️⃣ **즉시 구현 (1-2일)**: 시나리오 A

**이유:**
- 현재 클러스터가 없는 상태
- 빠른 클러스터 구축이 우선
- User-Data 16KB 제한은 S3/gzip으로 해결

**구현 계획:**
```
1. User-Data 스크립트 S3에 업로드
2. Terraform에서 간단한 user-data로 S3 스크립트 다운로드
3. Node Lifecycle Operator 배포 (이미 작성됨)
4. ArgoCD는 현재 방식 유지 (Helm)
```

#### 2️⃣ **중기 개선 (1-2개월)**: Cluster API 검토

**시기:**
- 클러스터가 안정화된 후
- 멀티 클러스터 필요성이 생길 때
- GitOps 완전 전환 시

**검토 사항:**
- Management Cluster 구축 방안
- CAPA + Kubeadm Bootstrap Provider 학습
- 현재 클러스터 Import 방법

#### 3️⃣ **장기 로드맵 (6개월~1년)**: Talos Linux 고려

**시기:**
- 보안 강화 필요 시
- 완전한 Immutable Infrastructure 구축 시
- 새로운 클러스터 추가 구축 시

---

## 📊 비교표

| 항목 | User-Data (현재) | Cluster API | Talos Linux |
|------|------------------|-------------|-------------|
| 구현 난이도 | ⭐ 쉬움 | ⭐⭐⭐⭐ 어려움 | ⭐⭐⭐ 보통 |
| 구현 시간 | 1-2일 | 1-2주 | 3-5일 |
| 유지보수성 | ⭐⭐ 보통 | ⭐⭐⭐⭐⭐ 매우 좋음 | ⭐⭐⭐⭐ 좋음 |
| 선언적 관리 | ❌ | ✅ | ✅ |
| GitOps 친화 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 멀티 클러스터 | ❌ | ✅ | ⭐⭐⭐ |
| 보안성 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 학습 곡선 | 낮음 | 매우 높음 | 높음 |
| 추가 인프라 | 불필요 | Management Cluster 필요 | 불필요 |

---

## 🔗 참고 자료

### Cluster API
- [Cluster API Book](https://cluster-api.sigs.k8s.io/)
- [CAPA (Cluster API Provider AWS)](https://github.com/kubernetes-sigs/cluster-api-provider-aws)
- [Kubeadm Bootstrap Provider](https://github.com/kubernetes-sigs/cluster-api/tree/main/bootstrap/kubeadm)

### OperatorHub.io
- [OperatorHub.io](https://operatorhub.io/)
- [ArgoCD Operator](https://operatorhub.io/operator/argocd-operator)
- [AWS Controllers for Kubernetes](https://aws-controllers-k8s.github.io/community/)

### Talos Linux
- [Talos Linux](https://www.talos.dev/)
- [Talos on AWS](https://www.talos.dev/v1.6/talos-guides/install/cloud-platforms/aws/)

### CNCF Projects
- [CNCF Landscape - Cluster Lifecycle](https://landscape.cncf.io/card-mode?category=certified-kubernetes-distribution,certified-kubernetes-hosted,certified-kubernetes-installer,special&grouping=category)

---

## 📝 최종 권장사항

**현재 상황:**
- ❌ 클러스터가 없는 상태
- ❌ 16KB user-data 제한 문제
- ✅ Node Lifecycle Operator는 이미 작성됨
- ✅ Kustomize, App-of-Apps 구조는 완성됨

**즉시 행동:**
1. **User-Data를 S3/gzip으로 최적화** ← 오늘 해결
2. **Terraform plan/apply로 클러스터 구축** ← 오늘 완료
3. **Node Lifecycle Operator 배포** ← 클러스터 구축 후
4. **ArgoCD로 App-of-Apps 배포** ← 최종 단계

**중장기 로드맵:**
- **Q1 2025**: Cluster API 학습 및 PoC
- **Q2 2025**: Cluster API 전환 (옵션)
- **Q3 2025**: Talos Linux 검토 (옵션)

**지금 당장은 시나리오 A를 구현하는 것이 최선입니다!** 🚀

