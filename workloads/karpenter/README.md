# Karpenter - Kubernetes Node Autoscaling

> Pending Pod 감지 → EC2 Fleet API로 최적 인스턴스 자동 프로비저닝
> KEDA(Pod) + Karpenter(Node) 조합으로 완전한 오토스케일링

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    KEDA + Karpenter 통합                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RabbitMQ 큐                                                │
│      │                                                      │
│      ▼                                                      │
│  ┌──────────┐                                              │
│  │   KEDA   │ → Pod 스케일 아웃 (3 → 10)                   │
│  └────┬─────┘                                              │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────┐                                              │
│  │Scheduler │ → 7개 Pod Pending (리소스 부족)              │
│  └────┬─────┘                                              │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────┐                                              │
│  │Karpenter │ → EC2 Fleet API 호출                         │
│  └────┬─────┘                                              │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────┐                                              │
│  │ EC2 Node │ → t3.large × 2 생성 (30-60초)                │
│  └──────────┘                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 디렉토리 구조

```
workloads/karpenter/
├── base/
│   ├── nodepool.yaml       # 프로비저닝 정책
│   ├── ec2nodeclass.yaml   # AWS EC2 설정
│   └── kustomization.yaml
├── dev/
│   └── kustomization.yaml  # Dev 오버레이
└── prod/
    └── kustomization.yaml  # Prod 오버레이
```

## 사전 요구사항

### 1. Terraform 변수 활성화

```bash
# terraform.tfvars
enable_karpenter = true
enable_irsa = true
```

### 2. Terraform Apply

```bash
cd terraform
terraform plan -var="dockerhub_password=xxx" -out=karpenter.plan
terraform apply karpenter.plan
```

### 3. Bootstrap Token 설정

kubeadm 클러스터에서 Karpenter가 새 노드를 join시키려면 Bootstrap Token이 필요합니다.

```bash
# Master 노드에서 실행
kubeadm token create --print-join-command

# 출력 예시:
# kubeadm join 10.0.1.21:6443 --token abc123.xyz789 \
#   --discovery-token-ca-cert-hash sha256:1234567890abcdef...

# Token과 CA Hash를 SSM에 저장
aws ssm put-parameter \
  --name "/sesacthon/dev/karpenter/bootstrap-token" \
  --value "abc123.xyz789" \
  --type "SecureString" \
  --overwrite

aws ssm put-parameter \
  --name "/sesacthon/dev/karpenter/ca-cert-hash" \
  --value "1234567890abcdef..." \
  --type "String" \
  --overwrite
```

### 4. ArgoCD Sync

```bash
# Karpenter Controller 배포
kubectl -n argocd annotate application dev-karpenter \
  argocd.argoproj.io/refresh=hard --overwrite

# NodePool CR 배포
kubectl -n argocd annotate application dev-karpenter-nodepool \
  argocd.argoproj.io/refresh=hard --overwrite
```

## 테스트

### Pending Pod 시뮬레이션

```bash
# 1. 현재 scan-worker Pod 수 확인
kubectl get pods -n scan -l app=scan-worker

# 2. Pod 수 강제 증가 (리소스 부족 유발)
kubectl scale deployment scan-worker -n scan --replicas=20

# 3. Pending Pod 확인
kubectl get pods -n scan -l app=scan-worker | grep Pending

# 4. Karpenter 로그 확인 (노드 프로비저닝)
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter -f

# 5. NodeClaim 확인
kubectl get nodeclaims

# 6. 새 노드 확인
kubectl get nodes -l managed-by=karpenter

# 7. Pod Running 확인
kubectl get pods -n scan -l app=scan-worker

# 8. 원래 상태로 복구
kubectl scale deployment scan-worker -n scan --replicas=3
```

### 노드 축소 테스트

```bash
# 1. Pod 수 감소
kubectl scale deployment scan-worker -n scan --replicas=1

# 2. Karpenter 노드 축소 확인 (30초 후)
kubectl get nodeclaims -w

# 3. 노드 제거 확인
kubectl get nodes
```

## 모니터링

### Prometheus 메트릭

```promql
# Karpenter가 관리하는 노드 수
count(kube_node_labels{label_managed_by="karpenter"})

# 프로비저닝 latency
histogram_quantile(0.99, karpenter_provisioner_scheduling_duration_seconds_bucket)

# Pending Pod 수
count(kube_pod_status_phase{phase="Pending"})
```

### 주요 대시보드 패널

- Active Karpenter Nodes
- Pending Pods Count
- Node Provisioning Latency
- Instance Type Distribution
- CPU/Memory Utilization per Node

## 트러블슈팅

### 노드가 생성되지 않는 경우

```bash
# 1. Karpenter 로그 확인
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter

# 2. NodeClaim 상태 확인
kubectl describe nodeclaim <name>

# 3. EC2 Quota 확인
aws service-quotas get-service-quota \
  --service-code ec2 \
  --quota-code L-1216C47A
```

### 노드 Join 실패

```bash
# 1. EC2 인스턴스 로그 확인 (AWS Console)
# System Log 또는 SSM Session Manager로 접근

# 2. Bootstrap Token 유효성 확인
kubeadm token list

# 3. 새 Token 생성
kubeadm token create --ttl 24h --print-join-command
```

### vCPU Quota 초과

```bash
# 현재 사용량 확인
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].InstanceType' \
  --output table

# Quota 증가 요청
aws service-quotas request-service-quota-increase \
  --service-code ec2 \
  --quota-code L-1216C47A \
  --desired-value 64
```

## 참고 문서

- [Foundation: Karpenter Node Autoscaling](../../docs/blogs/async/foundations/16-karpenter-node-autoscaling.md)
- [Karpenter Official Docs](https://karpenter.sh/docs/)
- [AWS Karpenter Best Practices](https://aws.github.io/aws-eks-best-practices/karpenter/)
