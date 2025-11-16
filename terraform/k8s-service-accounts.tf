# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Kubernetes ServiceAccounts with IRSA annotations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 목적: Helm이 생성하지 않도록 Terraform에서 ServiceAccount를 미리 생성
#       IRSA annotation을 동적으로 주입
# 참조: docs/architecture/gitops/ARGOCD_HELM_SECRET_INJECTION.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Provider for kubectl (Terraform can manage K8s resources after cluster is ready)
# Note: 실제 적용 시 kubernetes provider 설정 필요
# terraform {
#   required_providers {
#     kubectl = {
#       source  = "gavinbunney/kubectl"
#       version = "~> 1.14"
#     }
#   }
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ALB Controller ServiceAccount
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# resource "kubectl_manifest" "alb_controller_sa" {
#   yaml_body = <<YAML
# apiVersion: v1
# kind: ServiceAccount
# metadata:
#   name: aws-load-balancer-controller
#   namespace: kube-system
#   annotations:
#     eks.amazonaws.com/role-arn: ${aws_iam_role.alb_controller.arn}
#   labels:
#     app.kubernetes.io/name: aws-load-balancer-controller
#     app.kubernetes.io/managed-by: terraform
# YAML
#
#   depends_on = [aws_iam_role.alb_controller]
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ExternalSecrets Operator ServiceAccount
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# resource "kubectl_manifest" "external_secrets_sa" {
#   yaml_body = <<YAML
# apiVersion: v1
# kind: ServiceAccount
# metadata:
#   name: external-secrets-sa
#   namespace: platform-system
#   annotations:
#     eks.amazonaws.com/role-arn: ${aws_iam_role.external_secrets.arn}
# YAML
#
#   depends_on = [aws_iam_role.external_secrets]
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Postgres Operator ServiceAccount
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# resource "kubectl_manifest" "postgres_operator_sa" {
#   yaml_body = <<YAML
# apiVersion: v1
# kind: ServiceAccount
# metadata:
#   name: postgres-operator
#   namespace: data-system
#   annotations:
#     eks.amazonaws.com/role-arn: ${aws_iam_role.postgres_operator.arn}
# YAML
#
#   depends_on = [aws_iam_role.postgres_operator]
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Note: 위 리소스들은 주석 처리됨
# 
# 이유: Self-managed K8s에서는 IRSA가 아닌 일반 SA를 사용하므로,
#       workloads/rbac-storage/base/service-accounts.yaml에서 생성하고
#       annotation은 ExternalSecret으로 patch하는 방식 채택
#
# EKS 전환 시 주석 해제하고 kubectl provider 활성화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

