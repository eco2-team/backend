# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master Node Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "master_public_ip" {
  description = "Master 노드 Public IP (Elastic IP)"
  value       = aws_eip.master.public_ip
}

output "master_private_ip" {
  description = "Master 노드 Private IP"
  value       = module.master.private_ip
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Nodes Outputs (Phase 1&2: 5 nodes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# API-1: Auth
output "api_auth_public_ip" {
  description = "Auth API Public IP"
  value       = module.api_auth.public_ip
}

output "api_auth_private_ip" {
  description = "Auth API Private IP"
  value       = module.api_auth.private_ip
}

# API-2: My
output "api_my_public_ip" {
  description = "My API Public IP"
  value       = module.api_my.public_ip
}

output "api_my_private_ip" {
  description = "My API Private IP"
  value       = module.api_my.private_ip
}

# API-3: Scan
output "api_scan_public_ip" {
  description = "Scan API Public IP"
  value       = module.api_scan.public_ip
}

output "api_scan_private_ip" {
  description = "Scan API Private IP"
  value       = module.api_scan.private_ip
}

# API-4: Character
output "api_character_public_ip" {
  description = "Character API Public IP"
  value       = module.api_character.public_ip
}

output "api_character_private_ip" {
  description = "Character API Private IP"
  value       = module.api_character.private_ip
}

# API-5: Location
output "api_location_public_ip" {
  description = "Location API Public IP"
  value       = module.api_location.public_ip
}

output "api_location_private_ip" {
  description = "Location API Private IP"
  value       = module.api_location.private_ip
}

# Phase 3: Extended APIs (주석 처리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# # API-6: Info
# output "api_info_public_ip" {
#   description = "Info API Public IP"
#   value       = module.api_info.public_ip
# }

# output "api_info_private_ip" {
#   description = "Info API Private IP"
#   value       = module.api_info.private_ip
# }

# # API-7: Chat
# output "api_chat_public_ip" {
#   description = "Chat API Public IP"
#   value       = module.api_chat.public_ip
# }

# output "api_chat_private_ip" {
#   description = "Chat API Private IP"
#   value       = module.api_chat.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes Outputs (Phase 4: 주석 처리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# # Worker-1: Storage
# output "worker_storage_public_ip" {
#   description = "Worker Storage Public IP"
#   value       = module.worker_storage.public_ip
# }

# output "worker_storage_private_ip" {
#   description = "Worker Storage Private IP"
#   value       = module.worker_storage.private_ip
# }

# # Worker-2: AI
# output "worker_ai_public_ip" {
#   description = "Worker AI Public IP"
#   value       = module.worker_ai.public_ip
# }

# output "worker_ai_private_ip" {
#   description = "Worker AI Private IP"
#   value       = module.worker_ai.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure Nodes Outputs (Phase 1&2: PostgreSQL, Redis / Phase 4: RabbitMQ, Monitoring)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PostgreSQL (Phase 1)
output "postgresql_public_ip" {
  description = "PostgreSQL 노드 Public IP"
  value       = module.postgresql.public_ip
}

output "postgresql_private_ip" {
  description = "PostgreSQL 노드 Private IP"
  value       = module.postgresql.private_ip
}

# Redis (Phase 1)
output "redis_public_ip" {
  description = "Redis 노드 Public IP"
  value       = module.redis.public_ip
}

output "redis_private_ip" {
  description = "Redis 노드 Private IP"
  value       = module.redis.private_ip
}

# RabbitMQ (Phase 4: 주석 처리)
# output "rabbitmq_public_ip" {
#   description = "RabbitMQ 노드 Public IP"
#   value       = module.rabbitmq.public_ip
# }

# output "rabbitmq_private_ip" {
#   description = "RabbitMQ 노드 Private IP"
#   value       = module.rabbitmq.private_ip
# }

# Monitoring (Phase 4: 주석 처리)
# output "monitoring_public_ip" {
#   description = "Monitoring 노드 Public IP"
#   value       = module.monitoring.public_ip
# }

# output "monitoring_private_ip" {
#   description = "Monitoring 노드 Private IP"
#   value       = module.monitoring.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ansible Inventory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ansible_inventory" {
  description = "Ansible Inventory 내용 (SSM 방식)"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_instance_id       = module.master.instance_id
    master_private_ip        = module.master.private_ip
    api_auth_instance_id     = module.api_auth.instance_id
    api_auth_private_ip      = module.api_auth.private_ip
    api_my_instance_id       = module.api_my.instance_id
    api_my_private_ip        = module.api_my.private_ip
    api_scan_instance_id     = module.api_scan.instance_id
    api_scan_private_ip      = module.api_scan.private_ip
    api_character_instance_id = module.api_character.instance_id
    api_character_private_ip = module.api_character.private_ip
    api_location_instance_id = module.api_location.instance_id
    api_location_private_ip  = module.api_location.private_ip
    postgresql_instance_id   = module.postgresql.instance_id
    postgresql_private_ip    = module.postgresql.private_ip
    redis_instance_id        = module.redis.instance_id
    redis_private_ip         = module.redis.private_ip
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSH Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ssh_commands" {
  description = "SSH 접속 명령어 (Phase 1&2)"
  value = {
    master        = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${aws_eip.master.public_ip}"
    api_auth      = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.api_auth.public_ip}"
    api_my        = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.api_my.public_ip}"
    api_scan      = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.api_scan.public_ip}"
    api_character = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.api_character.public_ip}"
    api_location  = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.api_location.public_ip}"
    postgresql    = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.postgresql.public_ip}"
    redis         = "ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@${module.redis.public_ip}"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cluster Info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "cluster_info" {
  description = "클러스터 정보 요약 (Phase 1&2)"
  value = {
    vpc_id     = module.vpc.vpc_id
    master_ip  = aws_eip.master.public_ip
    phase      = "Phase 1&2 - MVP + Core APIs"
    api_ips = [
      module.api_auth.public_ip,
      module.api_my.public_ip,
      module.api_scan.public_ip,
      module.api_character.public_ip,
      module.api_location.public_ip
    ]
    infra_ips = [
      module.postgresql.public_ip,
      module.redis.public_ip
    ]
    # Phase 1&2: 8 nodes (Master + 5 APIs + PostgreSQL + Redis)
    total_nodes        = 8
    total_vcpu         = 16  # 2(master) + 2*4(auth,my,char,loc) + 2(scan) + 2(psql) + 2(redis)
    total_memory_gb    = 22  # 8(master) + 1*4(auth,my,char,loc) + 2(scan) + 4(psql) + 2(redis)
    estimated_cost_usd = 158 # t3.large*1 + t3.medium*1 + t3.small*2 + t3.micro*4
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Node Roles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "node_roles" {
  description = "노드별 역할 (Phase 1&2)"
  value = {
    master        = "Control Plane (t3.large, 8GB) - Phase 1"
    api_auth      = "Authentication API (t3.micro, 1GB) - Phase 1"
    api_my        = "My Page API (t3.micro, 1GB) - Phase 1"
    api_scan      = "Waste Scan API (t3.small, 2GB) - Phase 2"
    api_character = "Character & Mission API (t3.micro, 1GB) - Phase 2"
    api_location  = "Location & Map API (t3.micro, 1GB) - Phase 2"
    postgresql    = "PostgreSQL - 7 Domain Schemas (t3.medium, 4GB) - Phase 1"
    redis         = "Redis Cache (t3.small, 2GB) - Phase 1"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DNS Records
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "dns_records" {
  description = "생성된 DNS 레코드 (domain_name 설정 시)"
  value = var.domain_name != "" ? {
    apex_domain = "https://${var.domain_name}"
    www_url     = "https://www.${var.domain_name}"
    # API 서브도메인
    api_base    = "https://api.${var.domain_name}"
    auth_url    = "https://api.${var.domain_name}/auth"
    my_url      = "https://api.${var.domain_name}/my"
    scan_url    = "https://api.${var.domain_name}/scan"
    character_url = "https://api.${var.domain_name}/character"
    location_url = "https://api.${var.domain_name}/location"
    # 관리 도구 서브도메인
    argocd_url  = "https://argocd.${var.domain_name}"
    grafana_url = "https://grafana.${var.domain_name}"
    # CDN 서브도메인
    cdn_url     = "https://images.${var.domain_name}"
    nameservers = try(data.aws_route53_zone.main[0].name_servers, [])
  } : null
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# S3 & CloudFront
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "s3_bucket_info" {
  description = "S3 이미지 버킷 정보"
  value = {
    bucket_name = aws_s3_bucket.images.id
    bucket_arn  = aws_s3_bucket.images.arn
    region      = var.aws_region
  }
}

output "cloudfront_info" {
  description = "CloudFront CDN 정보"
  value = {
    distribution_id     = aws_cloudfront_distribution.images.id
    distribution_domain = aws_cloudfront_distribution.images.domain_name
    cdn_url            = "https://${aws_cloudfront_distribution.images.domain_name}"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Other Required Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "aws_region" {
  description = "AWS Region"
  value       = var.aws_region
}

output "acm_certificate_arn" {
  description = "ACM Certificate ARN (domain_name이 설정된 경우)"
  value       = var.domain_name != "" ? try(aws_acm_certificate_validation.main[0].certificate_arn, aws_acm_certificate.main[0].arn, "") : ""
}
