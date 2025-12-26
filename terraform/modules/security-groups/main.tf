# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Security Groups for Kubernetes Cluster
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 설계 원칙:
# 1. Security Group (AWS 인프라 레벨)
#    - SSH 접근 제어
#    - API Server 외부 접근
#    - 노드 간 자유 통신 (self 규칙)
#    - ALB -> 노드 트래픽
#
# 2. NetworkPolicy (Kubernetes Pod 레벨)
#    - Pod 간 통신 세밀 제어
#    - Tier별 격리 (business-logic, data)
#    - DNS, Monitoring 예외 처리
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Kubernetes Cluster Security Group
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master와 Worker 구분 없이 모든 클러스터 노드가 사용
# 노드 간 통신은 self 규칙으로 전체 허용
# Pod 간 세밀한 제어는 NetworkPolicy가 담당

resource "aws_security_group" "k8s_cluster" {
  name        = "${var.environment}-k8s-cluster-sg"
  description = "Security group for Kubernetes cluster nodes (master & workers)"
  vpc_id      = var.vpc_id

  tags = merge(
    {
      Name        = "${var.environment}-k8s-cluster-sg"
      Environment = var.environment
      ManagedBy   = "Terraform"
    },
    var.enable_karpenter ? {
      "karpenter.sh/discovery" = "true"
    } : {}
  )
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ingress Rules
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# SSH 접근
resource "aws_security_group_rule" "cluster_ssh" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = [var.allowed_ssh_cidr]
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "SSH from allowed CIDR"
}

# Kubernetes API Server (외부 접근)
resource "aws_security_group_rule" "cluster_api" {
  type              = "ingress"
  from_port         = 6443
  to_port           = 6443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "Kubernetes API Server"
}

# NodePort Services (외부 접근)
resource "aws_security_group_rule" "cluster_nodeport" {
  type              = "ingress"
  from_port         = 30000
  to_port           = 32767
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "NodePort Services"
}

# 클러스터 내부 통신 (모든 프로토콜/포트 허용)
# etcd, kubelet, kube-scheduler, kube-controller-manager, CNI 등
resource "aws_security_group_rule" "cluster_internal" {
  type              = "ingress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  self              = true
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "Cluster internal communication (etcd, kubelet, CNI, etc.)"
}

# Istio Pilot Webhook Validation (Explicit Rule)
resource "aws_security_group_rule" "cluster_istio_webhook" {
  type              = "ingress"
  from_port         = 15017
  to_port           = 15017
  protocol          = "tcp"
  self              = true
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "Istio Pilot Webhook Validation (15017)"
}

# Egress: 모든 아웃바운드 허용
resource "aws_security_group_rule" "cluster_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "Allow all outbound traffic"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ALB Security Group
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AWS Load Balancer Controller가 관리하는 ALB용

resource "aws_security_group" "alb" {
  name        = "${var.environment}-alb-sg"
  description = "Security group for AWS Load Balancer Controller managed ALBs"
  vpc_id      = var.vpc_id

  tags = {
    Name        = "${var.environment}-alb-sg"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# HTTP 인바운드
resource "aws_security_group_rule" "alb_http" {
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from internet"
}

# HTTPS 인바운드
resource "aws_security_group_rule" "alb_https" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from internet"
}

# ALB -> Cluster 아웃바운드
resource "aws_security_group_rule" "alb_to_cluster" {
  type                     = "egress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.k8s_cluster.id
  description              = "To cluster nodes"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ALB -> Cluster 트래픽 허용
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_security_group_rule" "cluster_from_alb" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.k8s_cluster.id
  source_security_group_id = aws_security_group.alb.id
  description              = "Allow traffic from ALB"
}
