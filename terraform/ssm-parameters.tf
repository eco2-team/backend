# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSM Parameter Store - Terraform Output Injection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 목적: VPC ID, Subnet ID, Security Group ID 등 인프라 식별자를 Git 노출 없이
#       Kubernetes ExternalSecrets / Ansible로 주입하기 위한 SSM Parameter 생성
# 참조: docs/architecture/gitops/TERRAFORM_SECRET_INJECTION.md
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

locals {
  secret_namespace = "/sesacthon/${var.environment}/cluster"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Network Resources
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "vpc_id" {
  name        = "/sesacthon/${var.environment}/network/vpc-id"
  type        = "String"
  value       = module.vpc.vpc_id
  description = "VPC ID for ${var.environment} cluster (ALB Controller)"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "network"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "public_subnet_ids" {
  name        = "/sesacthon/${var.environment}/network/public-subnets"
  type        = "StringList"
  value       = join(",", module.vpc.public_subnet_ids)
  description = "Public subnet IDs (ALB target)"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "network"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "private_subnet_ids" {
  name        = "/sesacthon/${var.environment}/network/private-subnets"
  type        = "StringList"
  value       = join(",", module.vpc.private_subnet_ids)
  description = "Private subnet IDs"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "network"
    Environment = var.environment
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Security Groups
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "alb_sg_id" {
  name        = "/sesacthon/${var.environment}/network/alb-sg-id"
  type        = "String"
  value       = module.security_groups.alb_sg_id
  description = "ALB Security Group ID"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "network"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "cluster_sg_id" {
  name        = "/sesacthon/${var.environment}/network/cluster-sg-id"
  type        = "String"
  value       = module.security_groups.cluster_sg_id
  description = "Kubernetes cluster nodes Security Group ID"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "network"
    Environment = var.environment
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. IAM Roles (IRSA)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "alb_controller_role_arn" {
  count       = var.enable_irsa ? 1 : 0
  name        = "/sesacthon/${var.environment}/iam/alb-controller-role-arn"
  type        = "String"
  value       = aws_iam_role.alb_controller[0].arn
  description = "ALB Controller IRSA Role ARN"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "iam"
    Environment = var.environment
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Cluster Metadata
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "cluster_region" {
  name        = "/sesacthon/${var.environment}/cluster/region"
  type        = "String"
  value       = var.aws_region
  description = "AWS Region"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "cluster"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "acm_certificate_arn" {
  count       = var.domain_name != "" ? 1 : 0
  name        = "/sesacthon/${var.environment}/ingress/acm-certificate-arn"
  type        = "String"
  value       = try(aws_acm_certificate_validation.main[0].certificate_arn, aws_acm_certificate.main[0].arn, "")
  description = "ACM Certificate ARN for HTTPS"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "ingress"
    Environment = var.environment
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Docker Hub Credentials
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

resource "aws_ssm_parameter" "dockerhub_username" {
  name        = "/sesacthon/${var.environment}/dockerhub/username"
  type        = "String"
  value       = var.dockerhub_username
  description = "Docker Hub username for private image pulls"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "dockerhub"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "dockerhub_password" {
  name        = "/sesacthon/${var.environment}/dockerhub/password"
  type        = "SecureString"
  value       = var.dockerhub_password
  description = "Docker Hub access token / PAT"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "dockerhub"
    Environment = var.environment
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Application Credentials (SecureString)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

locals {
  secret_special_chars = "!@#$%^&*()-_=+[]{}"
}

resource "random_password" "postgres_admin" {
  length           = 32
  special          = true
  override_special = local.secret_special_chars
}

resource "random_password" "redis_auth" {
  length           = 32
  special          = true
  override_special = local.secret_special_chars
}

resource "random_password" "rabbitmq_admin" {
  length           = 32
  special          = true
  override_special = local.secret_special_chars
}

resource "random_password" "argocd_admin" {
  length           = 32
  special          = true
  override_special = local.secret_special_chars
}

resource "random_password" "grafana_admin" {
  length           = 32
  special          = true
  override_special = local.secret_special_chars
}

resource "aws_ssm_parameter" "postgres_admin_password" {
  name        = "/sesacthon/${var.environment}/data/postgres-password"
  type        = "SecureString"
  value       = random_password.postgres_admin.result
  description = "PostgreSQL superuser password"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "data"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "redis_password" {
  name        = "/sesacthon/${var.environment}/data/redis-password"
  type        = "SecureString"
  value       = random_password.redis_auth.result
  description = "Redis authentication password"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "data"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "rabbitmq_password" {
  name        = "/sesacthon/${var.environment}/data/rabbitmq-password"
  type        = "SecureString"
  value       = random_password.rabbitmq_admin.result
  description = "RabbitMQ default user password"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "data"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "argocd_admin_password" {
  name        = "/sesacthon/${var.environment}/platform/argocd-admin-password"
  type        = "SecureString"
  value       = random_password.argocd_admin.result
  description = "ArgoCD admin password"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "platform"
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "grafana_admin_password" {
  name        = "/sesacthon/${var.environment}/platform/grafana-admin-password"
  type        = "SecureString"
  value       = random_password.grafana_admin.result
  description = "Grafana admin password"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "platform"
    Environment = var.environment
  }
}
