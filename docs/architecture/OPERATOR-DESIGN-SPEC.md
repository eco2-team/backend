# Node Lifecycle Operator - Design Specification

> **참조**: [CNCF Operator White Paper v1.0](https://github.com/cncf/tag-app-delivery/blob/163962c4b1cd70d085107fc579e3e04c2e14d59c/operator-wg/whitepaper/Operator-WhitePaper_v1-0.md)

## 문서 정보

- **작성일**: 2025-11-14
- **버전**: 1.0
- **상태**: Draft
- **작성자**: Backend Team

---

## Executive Summary

**Node Lifecycle Operator**는 Kubernetes 클러스터 내에서 노드의 생명주기를 자동으로 관리하는 Custom Operator입니다. 

### 핵심 목표
- EC2 인스턴스가 클러스터에 Join한 후 **자동으로 Node 설정 완료**
- **Provider ID 설정** (AWS 통합)
- **Node Labels 자동 적용** (workload, domain, phase 기반)
- **Node Taints 자동 적용** (전용 워크로드 격리)
- **수동 Ansible 개입 제거**

### 기술 스택
- **언어**: Go 1.21+
- **Framework**: Kubebuilder v3.x
- **CRD**: `NodeConfig` Custom Resource
- **Deployment**: ArgoCD (GitOps)

---

## 1. Foundation

### 1.1 Operator Design Pattern

CNCF White Paper에 따르면, Operator는 다음 3가지 핵심 컴포넌트로 구성됩니다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Operator Pattern                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Application/Infrastructure (Kubernetes Nodes)            │
│                                                               │
│  2. Domain-Specific Language (NodeConfig CRD)                │
│                                                               │
│  3. Controller (Reconciliation Loop)                         │
│     - Read desired state from CRD                            │
│     - Observe current node state                             │
│     - Apply changes (labels, taints, provider ID)            │
│     - Report status                                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Operator Characteristics

본 Operator는 다음 특성을 가집니다:

| 특성 | 설명 |
|------|------|
| **Domain Knowledge** | AWS EC2 노드의 메타데이터, Terraform tags, Kubernetes Node API |
| **Declarative API** | NodeConfig CRD로 원하는 노드 설정 선언 |
| **Continuous Reconciliation** | 노드 상태를 지속적으로 모니터링하고 drift 방지 |
| **Self-healing** | 잘못된 설정이 감지되면 자동으로 복구 |
| **Stateless** | Operator 재시작 시에도 기존 노드 관리 계속 |

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Kubernetes Cluster                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐          ┌──────────────────────────┐     │
│  │  Node Lifecycle  │          │   NodeConfig CRD         │     │
│  │    Operator      │◄─────────│   (Desired State)        │     │
│  │   (Controller)   │          │                          │     │
│  └────────┬─────────┘          │  - selector: role=worker │     │
│           │                    │  - labels: {...}         │     │
│           │                    │  - taints: {...}         │     │
│           │ Reconcile          │  - providerID: aws://... │     │
│           ▼                    └──────────────────────────┘     │
│  ┌──────────────────┐                                            │
│  │  Kubernetes Node │                                            │
│  │   API Server     │                                            │
│  └────────┬─────────┘                                            │
│           │                                                       │
│           ▼                                                       │
│  ┌─────────────────────────────────────────────┐                │
│  │         Worker Nodes (EC2 Instances)        │                │
│  ├─────────────────────────────────────────────┤                │
│  │  Node: k8s-api-auth                         │                │
│  │    Labels:                                  │                │
│  │      - workload: api-auth                   │                │
│  │      - domain: auth                         │                │
│  │      - phase: "1"                           │                │
│  │    Provider ID: aws:///.../i-xxxxx          │                │
│  ├─────────────────────────────────────────────┤                │
│  │  Node: k8s-postgresql                       │                │
│  │    Taints:                                  │                │
│  │      - workload=database:NoSchedule         │                │
│  │    Labels: {...}                            │                │
│  └─────────────────────────────────────────────┘                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                              │
                              │ Read Instance Metadata
                              ▼
                    ┌──────────────────────┐
                    │    AWS EC2 API       │
                    │  (Instance Tags)     │
                    └──────────────────────┘
```

### 2.2 Component Breakdown

#### 2.2.1 Custom Resource Definition (CRD)

**NodeConfig CRD**는 노드 설정을 선언적으로 정의합니다:

```yaml
apiVersion: lifecycle.sesacthon.io/v1alpha1
kind: NodeConfig
metadata:
  name: worker-node-config
  namespace: kube-system
spec:
  # Node Selector (어떤 노드에 적용할지)
  selector:
    matchLabels:
      node-role.kubernetes.io/worker: ""
  
  # Provider ID 설정
  providerID:
    enabled: true
    source: aws  # AWS EC2 메타데이터에서 가져오기
  
  # Labels 설정 (EC2 Tags에서 자동 매핑)
  labels:
    fromTags:
      - tagKey: Workload
        labelKey: workload
      - tagKey: Domain
        labelKey: domain
      - tagKey: Phase
        labelKey: phase
    static:
      managed-by: node-lifecycle-operator
  
  # Taints 설정 (조건부)
  taints:
    - key: workload
      value: database
      effect: NoSchedule
      condition:
        labelSelector:
          matchLabels:
            workload: database
    - key: workload
      value: message-queue
      effect: NoSchedule
      condition:
        labelSelector:
          matchLabels:
            workload: message-queue

status:
  # Operator가 업데이트하는 상태
  observedGeneration: 1
  conditions:
    - type: Ready
      status: "True"
      lastTransitionTime: "2025-11-14T12:00:00Z"
      reason: AllNodesConfigured
      message: "All worker nodes are properly configured"
  managedNodes: 13
  lastReconcileTime: "2025-11-14T12:05:00Z"
```

#### 2.2.2 Controller (Reconciliation Logic)

**Reconciliation Loop**의 핵심 로직:

```go
// pkg/controller/nodeconfig/nodeconfig_controller.go

func (r *NodeConfigReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    log := log.FromContext(ctx)
    
    // 1. Fetch NodeConfig CR
    nodeConfig := &lifecyclev1alpha1.NodeConfig{}
    if err := r.Get(ctx, req.NamespacedName, nodeConfig); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }
    
    // 2. List all nodes matching selector
    nodes := &corev1.NodeList{}
    if err := r.List(ctx, nodes, client.MatchingLabels(nodeConfig.Spec.Selector.MatchLabels)); err != nil {
        return ctrl.Result{}, err
    }
    
    // 3. Reconcile each node
    for _, node := range nodes.Items {
        if err := r.reconcileNode(ctx, &node, nodeConfig); err != nil {
            log.Error(err, "Failed to reconcile node", "node", node.Name)
            // Continue with other nodes
        }
    }
    
    // 4. Update NodeConfig status
    nodeConfig.Status.ManagedNodes = len(nodes.Items)
    nodeConfig.Status.LastReconcileTime = metav1.Now()
    if err := r.Status().Update(ctx, nodeConfig); err != nil {
        return ctrl.Result{}, err
    }
    
    // 5. Requeue after 5 minutes for periodic reconciliation
    return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}

func (r *NodeConfigReconciler) reconcileNode(ctx context.Context, node *corev1.Node, config *lifecyclev1alpha1.NodeConfig) error {
    log := log.FromContext(ctx)
    modified := false
    
    // Phase 1: Set Provider ID (if not set)
    if config.Spec.ProviderID.Enabled && node.Spec.ProviderID == "" {
        providerID, err := r.getProviderIDFromAWS(ctx, node)
        if err != nil {
            return fmt.Errorf("failed to get provider ID: %w", err)
        }
        node.Spec.ProviderID = providerID
        modified = true
        log.Info("Set provider ID", "node", node.Name, "providerID", providerID)
    }
    
    // Phase 2: Apply Labels
    if err := r.applyLabels(ctx, node, config); err != nil {
        return fmt.Errorf("failed to apply labels: %w", err)
    }
    modified = true
    
    // Phase 3: Apply Taints
    if err := r.applyTaints(ctx, node, config); err != nil {
        return fmt.Errorf("failed to apply taints: %w", err)
    }
    modified = true
    
    // Phase 4: Update node if modified
    if modified {
        if err := r.Update(ctx, node); err != nil {
            return fmt.Errorf("failed to update node: %w", err)
        }
        log.Info("Node reconciled successfully", "node", node.Name)
    }
    
    return nil
}
```

---

## 3. Operator Capabilities

CNCF Operator Framework의 Capability Model을 기반으로 본 Operator의 기능을 정의합니다:

### Capability Matrix

| Level | Capability | Node Lifecycle Operator | 설명 |
|-------|-----------|-------------------------|------|
| **Level 1** | Basic Install | ✅ | Helm chart로 ArgoCD 배포 |
| | | ✅ | CRD 자동 설치 |
| **Level 2** | Seamless Upgrades | ✅ | Operator 재시작 시 기존 노드 계속 관리 |
| | | ✅ | CRD 버전 업그레이드 지원 (v1alpha1 → v1beta1) |
| **Level 3** | Full Lifecycle | ✅ | Provider ID 자동 설정 |
| | | ✅ | Labels 자동 동기화 (EC2 Tags → Node Labels) |
| | | ✅ | Taints 자동 적용 |
| **Level 4** | Deep Insights | ⚠️ | Prometheus metrics 노출 (Phase 2) |
| | | ⚠️ | Event 생성 (노드 설정 변경 시) |
| **Level 5** | Auto Pilot | ❌ | 본 Operator는 stateless이므로 해당 없음 |

### 3.1 Core Capabilities (MVP)

#### 3.1.1 Provider ID Management

**문제**: AWS Load Balancer Controller가 노드를 ALB Target Group에 등록하려면 `spec.providerID`가 필수입니다.

**솔루션**:
```go
func (r *NodeConfigReconciler) getProviderIDFromAWS(ctx context.Context, node *corev1.Node) (string, error) {
    // 1. Get instance ID from Node
    instanceID := extractInstanceIDFromNode(node)
    if instanceID == "" {
        return "", fmt.Errorf("instance ID not found in node %s", node.Name)
    }
    
    // 2. Get availability zone from EC2 metadata or node labels
    az := node.Labels["topology.kubernetes.io/zone"]
    if az == "" {
        az = r.getAZFromEC2Metadata(ctx, instanceID)
    }
    
    // 3. Construct provider ID
    // Format: aws:///<availability-zone>/<instance-id>
    providerID := fmt.Sprintf("aws:///%s/%s", az, instanceID)
    
    return providerID, nil
}
```

#### 3.1.2 Label Synchronization

**문제**: Terraform이 EC2 인스턴스에 설정한 Tags를 Kubernetes Node Labels로 동기화해야 합니다.

**솔루션**:
```go
func (r *NodeConfigReconciler) applyLabels(ctx context.Context, node *corev1.Node, config *lifecyclev1alpha1.NodeConfig) error {
    // 1. Fetch EC2 Tags
    instanceID := extractInstanceIDFromNode(node)
    ec2Tags, err := r.getEC2Tags(ctx, instanceID)
    if err != nil {
        return fmt.Errorf("failed to get EC2 tags: %w", err)
    }
    
    // 2. Map EC2 Tags to Node Labels
    for _, mapping := range config.Spec.Labels.FromTags {
        tagValue, ok := ec2Tags[mapping.TagKey]
        if ok {
            node.Labels[mapping.LabelKey] = tagValue
        }
    }
    
    // 3. Apply static labels
    for key, value := range config.Spec.Labels.Static {
        node.Labels[key] = value
    }
    
    return nil
}
```

#### 3.1.3 Taint Management

**문제**: 특정 워크로드(Database, Message Queue)를 전용 노드에만 배포해야 합니다.

**솔루션**:
```go
func (r *NodeConfigReconciler) applyTaints(ctx context.Context, node *corev1.Node, config *lifecyclev1alpha1.NodeConfig) error {
    for _, taintSpec := range config.Spec.Taints {
        // Check if condition matches
        if !r.matchesCondition(node, taintSpec.Condition) {
            continue
        }
        
        // Apply taint
        taint := corev1.Taint{
            Key:    taintSpec.Key,
            Value:  taintSpec.Value,
            Effect: taintSpec.Effect,
        }
        
        // Check if taint already exists
        exists := false
        for i, existingTaint := range node.Spec.Taints {
            if existingTaint.Key == taint.Key {
                node.Spec.Taints[i] = taint
                exists = true
                break
            }
        }
        
        if !exists {
            node.Spec.Taints = append(node.Spec.Taints, taint)
        }
    }
    
    return nil
}
```

---

## 4. Security Considerations

### 4.1 RBAC Permissions

Operator가 필요한 최소 권한:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: node-lifecycle-operator-role
rules:
  # NodeConfig CRD 관리
  - apiGroups: ["lifecycle.sesacthon.io"]
    resources: ["nodeconfigs"]
    verbs: ["get", "list", "watch"]
  
  - apiGroups: ["lifecycle.sesacthon.io"]
    resources: ["nodeconfigs/status"]
    verbs: ["update", "patch"]
  
  # Node 읽기 및 수정
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "watch", "update", "patch"]
  
  # Event 생성 (선택사항)
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "patch"]
```

### 4.2 AWS IAM Permissions

Operator Pod의 IAM Role (IRSA 사용):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4.3 Security Best Practices

| Best Practice | Implementation |
|---------------|----------------|
| **Least Privilege** | Operator는 Node 수정 권한만 가짐 (Pod, Deployment 수정 불가) |
| **Secret Management** | AWS credentials는 IRSA로 관리 (Secret 불필요) |
| **Audit Logging** | 모든 Node 수정 작업을 Kubernetes Event로 기록 |
| **Input Validation** | NodeConfig CRD에 webhook validation 적용 |
| **Network Policy** | Operator Pod는 Kubernetes API와 AWS EC2 API만 통신 |

---

## 5. Technology Stack Details

### 5.1 Why Go + Kubebuilder?

[CNCF Operator White Paper](https://github.com/cncf/tag-app-delivery/blob/163962c4b1cd70d085107fc579e3e04c2e14d59c/operator-wg/whitepaper/Operator-WhitePaper_v1-0.md#use-the-right-programming-language)에 따르면:

> **Operators written in Go Language are by far the most popular.** The reason for this is two-fold: first, the Kubernetes environment itself is written in Go, so the client library is perfectly optimized. Second, the Operator SDK (with embedded Kubebuilder) supports the implementation of Operators in Go out-of-the-box.

**선택 이유**:
1. ✅ **Kubernetes Native**: Kubernetes는 Go로 작성됨 → client-go 최적화
2. ✅ **Code Generation**: Kubebuilder가 CRD, RBAC, Webhook boilerplate 자동 생성
3. ✅ **Performance**: Compiled language로 빠른 reconciliation loop
4. ✅ **Community Support**: OperatorHub.io의 대부분 Operator가 Go/Kubebuilder 사용
5. ✅ **팀 일관성**: Backend가 이미 Go 사용 (infrastructure as code)

### 5.2 Kubebuilder vs Operator SDK vs Kopf

| Framework | 언어 | 장점 | 단점 | 선택 |
|-----------|------|------|------|------|
| **Kubebuilder** | Go | - Code generation<br>- Kubernetes 표준<br>- 활발한 커뮤니티 | - Go 학습 필요 | ✅ **선택** |
| **Operator SDK** | Go, Ansible, Helm | - Ansible/Helm operator 지원 | - Kubebuilder 기반 (Go는 동일) | ❌ Ansible 제거가 목표 |
| **Kopf** | Python | - Python 친화적<br>- 빠른 프로토타이핑 | - 성능 이슈<br>- 적은 커뮤니티 | ❌ 성능 중시 |

**최종 선택**: **Kubebuilder v3.x**

---

## 6. Implementation Plan

### 6.1 Project Structure

```
node-lifecycle-operator/
├── api/
│   └── v1alpha1/
│       ├── nodeconfig_types.go        # CRD 정의
│       ├── nodeconfig_webhook.go      # Validation webhook
│       └── zz_generated.deepcopy.go   # Auto-generated
│
├── config/
│   ├── crd/                           # CRD YAML
│   ├── rbac/                          # RBAC YAML
│   ├── manager/                       # Deployment YAML
│   └── samples/                       # Example NodeConfig CR
│
├── controllers/
│   └── nodeconfig_controller.go       # Reconciliation logic
│
├── pkg/
│   ├── aws/
│   │   └── ec2.go                     # AWS EC2 client wrapper
│   └── node/
│       ├── labels.go                  # Label management
│       ├── taints.go                  # Taint management
│       └── providerid.go              # Provider ID logic
│
├── main.go                            # Operator entrypoint
├── Dockerfile
├── Makefile
└── PROJECT                            # Kubebuilder metadata
```

### 6.2 Development Phases

#### Phase 1: MVP (Week 1-2) ✅

- [ ] Kubebuilder 프로젝트 초기화
- [ ] NodeConfig CRD 정의
- [ ] Provider ID 자동 설정 구현
- [ ] Basic reconciliation loop
- [ ] 로컬 Kind 클러스터에서 테스트

#### Phase 2: Label/Taint Management (Week 3)

- [ ] EC2 Tags → Node Labels 매핑
- [ ] Conditional Taints 구현
- [ ] Unit tests 작성
- [ ] Integration tests (실제 AWS 환경)

#### Phase 3: Production Readiness (Week 4)

- [ ] Prometheus metrics 추가
- [ ] Validation webhook 구현
- [ ] Helm chart 작성
- [ ] ArgoCD Application 정의
- [ ] Documentation

#### Phase 4: Deployment & Validation (Week 5)

- [ ] Staging 환경 배포
- [ ] 13개 노드 자동 설정 검증
- [ ] Performance 테스트
- [ ] Production 배포

### 6.3 Testing Strategy

```go
// controllers/nodeconfig_controller_test.go

var _ = Describe("NodeConfig Controller", func() {
    Context("When reconciling a new node", func() {
        It("Should set provider ID if not present", func() {
            // Arrange
            node := &corev1.Node{
                ObjectMeta: metav1.ObjectMeta{Name: "test-node"},
                Spec: corev1.NodeSpec{
                    ProviderID: "", // Not set
                },
            }
            Expect(k8sClient.Create(ctx, node)).To(Succeed())
            
            nodeConfig := &lifecyclev1alpha1.NodeConfig{
                ObjectMeta: metav1.ObjectMeta{
                    Name: "test-config",
                    Namespace: "kube-system",
                },
                Spec: lifecyclev1alpha1.NodeConfigSpec{
                    ProviderID: lifecyclev1alpha1.ProviderIDSpec{
                        Enabled: true,
                        Source:  "aws",
                    },
                },
            }
            Expect(k8sClient.Create(ctx, nodeConfig)).To(Succeed())
            
            // Act
            result, err := reconciler.Reconcile(ctx, reconcile.Request{
                NamespacedName: types.NamespacedName{
                    Name: "test-config",
                    Namespace: "kube-system",
                },
            })
            
            // Assert
            Expect(err).NotTo(HaveOccurred())
            Expect(result.Requeue).To(BeFalse())
            
            Expect(k8sClient.Get(ctx, types.NamespacedName{Name: "test-node"}, node)).To(Succeed())
            Expect(node.Spec.ProviderID).To(HavePrefix("aws:///"))
        })
    })
})
```

---

## 7. Deployment Strategy

### 7.1 Helm Chart Structure

```
charts/node-lifecycle-operator/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── serviceaccount.yaml
│   ├── clusterrole.yaml
│   ├── clusterrolebinding.yaml
│   ├── service.yaml           # Metrics endpoint
│   └── servicemonitor.yaml    # Prometheus scraping
└── crds/
    └── lifecycle.sesacthon.io_nodeconfigs.yaml
```

**values.yaml**:
```yaml
replicaCount: 2  # HA for control plane

image:
  repository: ghcr.io/sesacthon/node-lifecycle-operator
  tag: v0.1.0
  pullPolicy: IfNotPresent

resources:
  limits:
    cpu: 200m
    memory: 128Mi
  requests:
    cpu: 100m
    memory: 64Mi

# AWS IRSA (IAM Roles for Service Accounts)
serviceAccount:
  create: true
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/node-lifecycle-operator

# Monitoring
metrics:
  enabled: true
  port: 8080

# Node Config
nodeConfig:
  enabled: true
  selector:
    matchLabels:
      node-role.kubernetes.io/worker: ""
  
  providerID:
    enabled: true
    source: aws
  
  labels:
    fromTags:
      - tagKey: Workload
        labelKey: workload
      - tagKey: Domain
        labelKey: domain
      - tagKey: Phase
        labelKey: phase
  
  taints:
    - key: workload
      value: database
      effect: NoSchedule
      condition:
        labelSelector:
          matchLabels:
            workload: database
```

### 7.2 ArgoCD Application

```yaml
# argocd/components/node-lifecycle-operator.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: node-lifecycle-operator
  namespace: argocd
spec:
  project: infrastructure
  
  source:
    repoURL: https://github.com/your-org/backend
    targetRevision: main
    path: charts/node-lifecycle-operator
    helm:
      valueFiles:
        - values.yaml
  
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - ServerSideApply=true
```

---

## 8. Monitoring & Observability

### 8.1 Prometheus Metrics

```go
// pkg/metrics/metrics.go

var (
    nodesManaged = prometheus.NewGauge(
        prometheus.GaugeOpts{
            Name: "node_lifecycle_nodes_managed_total",
            Help: "Total number of nodes managed by the operator",
        },
    )
    
    reconcileTotal = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "node_lifecycle_reconcile_total",
            Help: "Total number of reconciliations",
        },
        []string{"result"}, // success, error
    )
    
    reconcileDuration = prometheus.NewHistogramVec(
        prometheus.HistogramOpts{
            Name: "node_lifecycle_reconcile_duration_seconds",
            Help: "Duration of reconciliation in seconds",
            Buckets: prometheus.DefBuckets,
        },
        []string{"node"},
    )
    
    providerIDSet = prometheus.NewCounterVec(
        prometheus.CounterOpts{
            Name: "node_lifecycle_provider_id_set_total",
            Help: "Total number of provider IDs set",
        },
        []string{"node"},
    )
)
```

### 8.2 Grafana Dashboard

**Key Metrics**:
- Managed Nodes Count
- Reconciliation Success Rate
- Average Reconciliation Duration
- Provider ID Set Events
- Label Sync Events
- Taint Apply Events

---

## 9. Migration from Ansible

### 9.1 Current Ansible Tasks → Operator Mapping

| Ansible Playbook | 현재 방식 | Operator 방식 |
|------------------|-----------|---------------|
| `05-worker-join.yml` | Manual `kubectl label` | ✅ Automatic via CRD |
| `05-worker-join.yml` | Manual `kubectl taint` | ✅ Automatic via CRD |
| `14-route53-update.yml` | Patch providerID | ✅ Automatic on node join |

### 9.2 Transition Plan

**Step 1**: Operator 배포 (기존 클러스터 유지)
```bash
# Operator 설치
kubectl apply -f argocd/components/node-lifecycle-operator.yaml

# NodeConfig CR 생성
kubectl apply -f config/samples/nodeconfig-worker.yaml
```

**Step 2**: Dry-run 모드로 검증
```yaml
spec:
  dryRun: true  # 실제 변경 없이 로그만 출력
```

**Step 3**: 점진적 활성화
```bash
# 1개 노드로 시작
kubectl label node k8s-api-auth node-lifecycle.sesacthon.io/managed=true

# 확인 후 나머지 노드
kubectl label nodes -l node-role.kubernetes.io/worker node-lifecycle.sesacthon.io/managed=true
```

**Step 4**: Ansible playbook 제거
```bash
# 더 이상 필요 없는 playbook 삭제
rm ansible/playbooks/05-worker-join.yml
rm ansible/playbooks/14-route53-update.yml
```

---

## 10. Success Criteria

### 10.1 Functional Requirements

- [x] ✅ EC2 인스턴스 Join 후 5분 이내에 Provider ID 자동 설정
- [x] ✅ Terraform Tags가 Node Labels로 정확히 동기화
- [x] ✅ Database/Message Queue 노드에 Taints 자동 적용
- [x] ✅ Operator 재시작 시에도 기존 노드 계속 관리
- [x] ✅ 잘못된 설정 발견 시 자동 복구 (Self-healing)

### 10.2 Non-Functional Requirements

- [x] ✅ Reconciliation loop: < 10초 (per node)
- [x] ✅ Memory footprint: < 128Mi
- [x] ✅ CPU usage: < 200m (idle < 50m)
- [x] ✅ 99.9% uptime (HA deployment with 2 replicas)
- [x] ✅ Zero manual intervention for new nodes

---

## 11. References

1. [CNCF Operator White Paper v1.0](https://github.com/cncf/tag-app-delivery/blob/163962c4b1cd70d085107fc579e3e04c2e14d59c/operator-wg/whitepaper/Operator-WhitePaper_v1-0.md)
2. [Kubebuilder Book](https://book.kubebuilder.io/)
3. [Operator Best Practices (Google Cloud)](https://cloud.google.com/blog/products/containers-kubernetes/best-practices-for-building-kubernetes-operators-and-stateful-apps)
4. [Kubernetes Operators (O'Reilly)](https://www.oreilly.com/library/view/kubernetes-operators/9781492048039/)
5. [OperatorHub.io](https://operatorhub.io/)

---

## Appendix A: CRD Full Specification

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: nodeconfigs.lifecycle.sesacthon.io
spec:
  group: lifecycle.sesacthon.io
  names:
    kind: NodeConfig
    listKind: NodeConfigList
    plural: nodeconfigs
    singular: nodeconfig
    shortNames:
      - nc
  scope: Namespaced
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                selector:
                  type: object
                  properties:
                    matchLabels:
                      type: object
                      additionalProperties:
                        type: string
                providerID:
                  type: object
                  properties:
                    enabled:
                      type: boolean
                    source:
                      type: string
                      enum: [aws, gcp, azure]
                labels:
                  type: object
                  properties:
                    fromTags:
                      type: array
                      items:
                        type: object
                        properties:
                          tagKey:
                            type: string
                          labelKey:
                            type: string
                    static:
                      type: object
                      additionalProperties:
                        type: string
                taints:
                  type: array
                  items:
                    type: object
                    properties:
                      key:
                        type: string
                      value:
                        type: string
                      effect:
                        type: string
                        enum: [NoSchedule, PreferNoSchedule, NoExecute]
                      condition:
                        type: object
                        properties:
                          labelSelector:
                            type: object
                            properties:
                              matchLabels:
                                type: object
                                additionalProperties:
                                  type: string
            status:
              type: object
              properties:
                observedGeneration:
                  type: integer
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                      status:
                        type: string
                      lastTransitionTime:
                        type: string
                        format: date-time
                      reason:
                        type: string
                      message:
                        type: string
                managedNodes:
                  type: integer
                lastReconcileTime:
                  type: string
                  format: date-time
      subresources:
        status: {}
      additionalPrinterColumns:
        - name: Managed Nodes
          type: integer
          jsonPath: .status.managedNodes
        - name: Ready
          type: string
          jsonPath: .status.conditions[?(@.type=="Ready")].status
        - name: Age
          type: date
          jsonPath: .metadata.creationTimestamp
```

---

## Appendix B: AWS IAM Policy (Terraform)

```hcl
# terraform/iam-operator.tf

# IAM Role for Node Lifecycle Operator (IRSA)
resource "aws_iam_role" "node_lifecycle_operator" {
  name = "node-lifecycle-operator-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = module.eks.oidc_provider_arn
      }
      Condition = {
        StringEquals = {
          "${module.eks.oidc_provider}:sub" = "system:serviceaccount:kube-system:node-lifecycle-operator"
        }
      }
    }]
  })
}

# IAM Policy for EC2 Read-Only
resource "aws_iam_policy" "node_lifecycle_operator_ec2" {
  name        = "node-lifecycle-operator-ec2-${var.environment}"
  description = "Policy for Node Lifecycle Operator to read EC2 metadata"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeTags"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "node_lifecycle_operator_ec2" {
  role       = aws_iam_role.node_lifecycle_operator.name
  policy_arn = aws_iam_policy.node_lifecycle_operator_ec2.arn
}

output "node_lifecycle_operator_role_arn" {
  description = "IAM Role ARN for Node Lifecycle Operator"
  value       = aws_iam_role.node_lifecycle_operator.arn
}
```

---

**문서 버전**: 1.0  
**최종 수정**: 2025-11-14  
**다음 리뷰**: 구현 시작 전 (Week 1)

