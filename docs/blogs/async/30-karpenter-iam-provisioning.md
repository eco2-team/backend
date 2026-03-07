# Karpenter IAM 프로비저닝 로그

> **작성일**: 2024-12-26  
> **환경**: dev (ap-northeast-2)  
> **목적**: Karpenter Node Autoscaling을 위한 IAM 리소스 프로비저닝

---

## 1. 개요

### 1.1. Karpenter란?

Karpenter는 AWS에서 개발한 Kubernetes 노드 오토스케일러입니다.

**기존 Cluster Autoscaler와의 차이:**

| 항목 | Cluster Autoscaler | Karpenter |
|------|-------------------|-----------|
| 스케일링 단위 | Node Group (ASG) | 개별 인스턴스 |
| 인스턴스 선택 | 사전 정의된 타입만 | 실시간 최적 선택 |
| 프로비저닝 시간 | 3-5분 | 60-90초 |
| Pending Pod 대응 | Node Group 확장 | 즉시 최적 인스턴스 생성 |

### 1.2. 도입 배경

```
문제: worker-ai 노드 리소스 부족 → scan-worker Pod Pending
원인: KEDA가 Pod를 스케일업했지만, 노드 리소스가 부족
해결: Karpenter로 Pending Pod 감지 시 자동 노드 프로비저닝
```

---

## 2. IAM 리소스 설계

### 2.1. kubeadm 클러스터의 제약

EKS와 달리 kubeadm 클러스터는 **OIDC Provider가 없어서 IRSA 사용 불가**.

**해결 방안: EC2 Instance Profile 방식**

```
┌─────────────────────────────────────────────────────────────┐
│ Master Node (k8s-master)                                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ IAM Role: k8s-node-role-dev                             │ │
│ │ ├── 기존 권한 (ECR, S3, CloudWatch, EBS)                │ │
│ │ └── + KarpenterControllerPolicy (EC2 Fleet API)         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Karpenter Controller Pod                                    │
│ → Master Node의 Instance Profile 권한 상속                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Karpenter가 생성하는 노드                                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ IAM Role: dev-karpenter-node                            │ │
│ │ Instance Profile: dev-karpenter-node                    │ │
│ │ ├── ECR Read                                            │ │
│ │ ├── S3 Access                                           │ │
│ │ ├── CloudWatch Logs                                     │ │
│ │ ├── EBS CSI                                             │ │
│ │ └── SSM Managed Instance                                │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2. 생성된 IAM 리소스

| 리소스 | 이름 | 용도 |
|--------|------|------|
| IAM Role Policy | `KarpenterControllerPolicy` | EC2 Fleet API 권한 (k8s-node-role-dev에 연결) |
| IAM Role | `dev-karpenter-node` | Karpenter가 생성하는 노드용 |
| Instance Profile | `dev-karpenter-node` | EC2 인스턴스에 Role 연결 |

---

## 3. Terraform 적용 로그

### 3.1. Plan 실행

```bash
cd terraform

terraform plan \
  -target=aws_iam_role_policy.karpenter_controller \
  -target=aws_iam_role.karpenter_node \
  -target=aws_iam_instance_profile.karpenter_node \
  -var="enable_karpenter=true" \
  -var="dockerhub_password=xxx" \
  -out=karpenter-only.plan
```

**Plan 결과:**
```
Terraform will perform the following actions:

  # aws_iam_role_policy.karpenter_controller[0] will be created
  + resource "aws_iam_role_policy" "karpenter_controller" {
      + name   = "KarpenterControllerPolicy"
      + role   = "k8s-node-role-dev"
      + policy = jsonencode({
          Statement = [
            {
              Sid      = "EC2NodeProvisioning"
              Effect   = "Allow"
              Action   = [
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
                "ec2:DescribeSpotPriceHistory",
                "ec2:CreateLaunchTemplate",
                "ec2:DeleteLaunchTemplate"
              ]
              Resource = "*"
            },
            {
              Sid      = "EC2TagManagement"
              Effect   = "Allow"
              Action   = ["ec2:CreateTags", "ec2:DeleteTags"]
              Resource = [
                "arn:aws:ec2:ap-northeast-2:721622471953:instance/*",
                "arn:aws:ec2:ap-northeast-2:721622471953:volume/*",
                "arn:aws:ec2:ap-northeast-2:721622471953:network-interface/*",
                "arn:aws:ec2:ap-northeast-2:721622471953:launch-template/*",
                "arn:aws:ec2:ap-northeast-2:721622471953:spot-instances-request/*"
              ]
            },
            {
              Sid       = "IAMPassRole"
              Effect    = "Allow"
              Action    = "iam:PassRole"
              Resource  = [
                "arn:aws:iam::721622471953:role/k8s-node-role-dev",
                "arn:aws:iam::721622471953:role/dev-karpenter-node"
              ]
              Condition = {
                StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" }
              }
            },
            {
              Sid      = "SSMGetParameter"
              Effect   = "Allow"
              Action   = "ssm:GetParameter"
              Resource = [
                "arn:aws:ssm:ap-northeast-2::parameter/aws/service/eks/optimized-ami/*",
                "arn:aws:ssm:ap-northeast-2::parameter/aws/service/canonical/ubuntu/*"
              ]
            },
            {
              Sid      = "PricingAPI"
              Effect   = "Allow"
              Action   = "pricing:GetProducts"
              Resource = "*"
            }
          ]
        })
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

### 3.2. Apply 실행

```bash
terraform apply "karpenter-only.plan"
```

**결과:**
```
aws_iam_role_policy.karpenter_controller[0]: Creating...
aws_iam_role_policy.karpenter_controller[0]: Creation complete after 2s [id=k8s-node-role-dev:KarpenterControllerPolicy]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

### 3.3. 생성된 리소스 ARN

| 리소스 | ARN/이름 |
|--------|----------|
| Karpenter Node Role | `arn:aws:iam::721622471953:role/dev-karpenter-node` |
| Karpenter Instance Profile | `dev-karpenter-node` |
| Controller Policy | `k8s-node-role-dev:KarpenterControllerPolicy` |

---

## 4. 권한 상세

### 4.1. KarpenterControllerPolicy

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
        "ec2:DescribeSpotPriceHistory",
        "ec2:CreateLaunchTemplate",
        "ec2:DeleteLaunchTemplate"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2TagManagement",
      "Effect": "Allow",
      "Action": ["ec2:CreateTags", "ec2:DeleteTags"],
      "Resource": [
        "arn:aws:ec2:ap-northeast-2:721622471953:instance/*",
        "arn:aws:ec2:ap-northeast-2:721622471953:volume/*",
        "arn:aws:ec2:ap-northeast-2:721622471953:network-interface/*",
        "arn:aws:ec2:ap-northeast-2:721622471953:launch-template/*",
        "arn:aws:ec2:ap-northeast-2:721622471953:spot-instances-request/*"
      ]
    },
    {
      "Sid": "IAMPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::721622471953:role/k8s-node-role-dev",
        "arn:aws:iam::721622471953:role/dev-karpenter-node"
      ],
      "Condition": {
        "StringEquals": { "iam:PassedToService": "ec2.amazonaws.com" }
      }
    },
    {
      "Sid": "SSMGetParameter",
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": [
        "arn:aws:ssm:ap-northeast-2::parameter/aws/service/eks/optimized-ami/*",
        "arn:aws:ssm:ap-northeast-2::parameter/aws/service/canonical/ubuntu/*"
      ]
    },
    {
      "Sid": "PricingAPI",
      "Effect": "Allow",
      "Action": "pricing:GetProducts",
      "Resource": "*"
    }
  ]
}
```

### 4.2. dev-karpenter-node Role

Karpenter가 프로비저닝하는 노드에 부여되는 권한:

- **ECR Read**: 컨테이너 이미지 풀
- **S3 Access**: 이미지 저장소 접근
- **CloudWatch Logs**: 로그 전송
- **EBS CSI**: 볼륨 마운트
- **SSM Managed Instance**: Session Manager 접속

---

## 5. 다음 단계

### 5.1. 남은 작업

| 단계 | 내용 | 상태 |
|------|------|------|
| 1 | Terraform IAM 리소스 생성 | ✅ 완료 |
| 2 | VPC 서브넷/SG에 Discovery 태그 추가 | ✅ 완료 |
| 3 | Karpenter Controller 배포 (ArgoCD) | ⏳ 대기 |
| 4 | NodePool/EC2NodeClass CR 배포 (ArgoCD) | ⏳ 대기 |
| 5 | Bootstrap Token SSM 저장 | ⏳ 대기 |
| 6 | 테스트: Pending Pod → 노드 자동 생성 | ⏳ 대기 |

### 5.2. Discovery 태그 적용 (완료)

Karpenter가 서브넷과 보안 그룹을 찾기 위한 태그:

```bash
terraform plan \
  -target=module.vpc.aws_subnet.public \
  -target=module.security_groups.aws_security_group.k8s_cluster \
  -var="enable_karpenter=true" \
  -var="dockerhub_password=xxx" \
  -out=karpenter-discovery-tags.plan

terraform apply karpenter-discovery-tags.plan
```

**결과:**
```
module.vpc.aws_subnet.public[0]: Modifications complete after 1s
module.vpc.aws_subnet.public[1]: Modifications complete after 1s
module.vpc.aws_subnet.public[2]: Modifications complete after 1s
module.security_groups.aws_security_group.k8s_cluster: Modifications complete after 1s

Apply complete! Resources: 0 added, 4 changed, 0 destroyed.
```

**태그가 추가된 리소스:**

| 리소스 | ID | 태그 |
|--------|-----|------|
| public-subnet-1 | subnet-0ed6e41a358444082 | `karpenter.sh/discovery=true` |
| public-subnet-2 | subnet-06132d5fee79482cf | `karpenter.sh/discovery=true` |
| public-subnet-3 | subnet-0a80d98615611b076 | `karpenter.sh/discovery=true` |
| k8s-cluster-sg | sg-06110b058db26dc92 | `karpenter.sh/discovery=true` |

### 5.3. ArgoCD 배포

```bash
# Git push 후 ArgoCD sync
kubectl get application dev-karpenter -n argocd
kubectl get application dev-karpenter-nodepool -n argocd
```

---

## 6. 관련 파일

| 파일 | 설명 |
|------|------|
| `terraform/karpenter-iam.tf` | IAM 리소스 정의 |
| `terraform/variables.tf` | `enable_karpenter` 변수 |
| `clusters/dev/apps/37-karpenter.yaml` | Karpenter Controller App |
| `clusters/dev/apps/38-karpenter-nodepool.yaml` | NodePool CR App |
| `workloads/karpenter/base/nodepool.yaml` | NodePool CR |
| `workloads/karpenter/base/ec2nodeclass.yaml` | EC2NodeClass CR |
| `docs/blogs/async/foundations/16-karpenter-node-autoscaling.md` | 기초 문서 |

---

## 7. 참고 자료

- [Karpenter 공식 문서](https://karpenter.sh/docs/)
- [Karpenter GitHub](https://github.com/aws/karpenter-provider-aws)
- [kubeadm 클러스터에서 Karpenter 사용](https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/)

