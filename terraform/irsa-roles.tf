# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IRSA (IAM Roles for Service Accounts)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 목적: Kubernetes ServiceAccount에 AWS IAM 권한을 할당
# 참조: docs/architecture/operations/RBAC_NAMESPACE_POLICY.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# OIDC Provider Data (EKS 클러스터용, Self-managed K8s는 별도 구성 필요)
# Self-managed의 경우 Service Account Token Projection 사용
locals {
  oidc_provider_arn = try(aws_iam_openid_connect_provider.cluster[0].arn, "")
  oidc_provider_url = try(trim(replace(aws_iam_openid_connect_provider.cluster[0].url, "https://", ""), "/"), "")
}

data "aws_caller_identity" "current" {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ALB Controller IRSA (이미 alb-controller-iam.tf에 정의됨 - 참조용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# aws_iam_role.alb_controller (기존)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ExternalSecrets Operator IRSA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_iam_role" "external_secrets" {
  count = var.enable_irsa ? 1 : 0
  name  = "${var.environment}-external-secrets-operator"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:platform-system:external-secrets-sa"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = {
    Name        = "${var.environment}-external-secrets-operator"
    Description = "IRSA for ExternalSecrets Operator (SSM Parameter Store Read)"
  }
}

resource "aws_iam_role_policy" "external_secrets_ssm" {
  count = var.enable_irsa ? 1 : 0
  name  = "SSMParameterStoreRead"
  role  = aws_iam_role.external_secrets[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/sesacthon/${var.environment}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:/sesacthon/${var.environment}/*"
      }
    ]
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ExternalDNS IRSA (Route53)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_iam_role" "external_dns" {
  count = var.enable_irsa ? 1 : 0
  name  = "${var.environment}-external-dns"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:platform-system:external-dns"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = {
    Name        = "${var.environment}-external-dns"
    Description = "IRSA for ExternalDNS (Route53 sync)"
  }
}

resource "aws_iam_role_policy" "external_dns_route53" {
  count = var.enable_irsa ? 1 : 0
  name  = "Route53ChangeRecords"
  role  = aws_iam_role.external_dns[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "route53:ListHostedZones",
          "route53:ListResourceRecordSets",
          "route53:ChangeResourceRecordSets"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "route53:ListTagsForResource"
        ]
        Resource = "*"
      }
    ]
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Postgres Operator IRSA (S3 Backup)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_iam_role" "postgres_operator" {
  count = var.enable_irsa ? 1 : 0
  name  = "${var.environment}-postgres-operator"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = local.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_provider_url}:sub" = "system:serviceaccount:data-system:postgres-operator"
          "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "postgres_s3_backup" {
  count = var.enable_irsa ? 1 : 0
  name  = "S3BackupAccess"
  role  = aws_iam_role.postgres_operator[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = [
        "arn:aws:s3:::sesacthon-pg-backup-${var.environment}",
        "arn:aws:s3:::sesacthon-pg-backup-${var.environment}/*",
        "arn:aws:s3:::sesacthon-pg-wal-${var.environment}",
        "arn:aws:s3:::sesacthon-pg-wal-${var.environment}/*"
      ]
    }]
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSM Parameters for IRSA ARNs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "external_secrets_role_arn" {
  count       = var.enable_irsa ? 1 : 0
  name        = "/sesacthon/${var.environment}/iam/external-secrets-role-arn"
  type        = "String"
  value       = aws_iam_role.external_secrets[0].arn
  description = "ExternalSecrets Operator IRSA Role ARN"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "iam"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "postgres_operator_role_arn" {
  count       = var.enable_irsa ? 1 : 0
  name        = "/sesacthon/${var.environment}/iam/postgres-operator-role-arn"
  type        = "String"
  value       = aws_iam_role.postgres_operator[0].arn
  description = "Postgres Operator IRSA Role ARN"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "iam"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "external_dns_role_arn" {
  count       = var.enable_irsa ? 1 : 0
  name        = "/sesacthon/${var.environment}/iam/external-dns-role-arn"
  type        = "String"
  value       = aws_iam_role.external_dns[0].arn
  description = "ExternalDNS IRSA Role ARN"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "iam"
    Environment = var.environment
  }
}
