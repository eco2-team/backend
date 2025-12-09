# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master Node Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "master_instance_id" {
  description = "Master 노드 Instance ID"
  value       = module.master.instance_id
}

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
output "api_auth_instance_id" {
  description = "Auth API Instance ID"
  value       = module.api_auth.instance_id
}

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
output "api_my_instance_id" {
  description = "My API Instance ID"
  value       = module.api_my.instance_id
}

output "api_my_public_ip" {
  description = "My API Public IP"
  value       = module.api_my.public_ip
}

output "api_my_private_ip" {
  description = "My API Private IP"
  value       = module.api_my.private_ip
}

# API-3: Scan
output "api_scan_instance_id" {
  description = "Scan API Instance ID"
  value       = module.api_scan.instance_id
}

output "api_scan_public_ip" {
  description = "Scan API Public IP"
  value       = module.api_scan.public_ip
}

output "api_scan_private_ip" {
  description = "Scan API Private IP"
  value       = module.api_scan.private_ip
}

# API-4: Character
output "api_character_instance_id" {
  description = "Character API Instance ID"
  value       = module.api_character.instance_id
}

output "api_character_public_ip" {
  description = "Character API Public IP"
  value       = module.api_character.public_ip
}

output "api_character_private_ip" {
  description = "Character API Private IP"
  value       = module.api_character.private_ip
}

# API-5: Location
output "api_location_instance_id" {
  description = "Location API Instance ID"
  value       = module.api_location.instance_id
}

output "api_location_public_ip" {
  description = "Location API Public IP"
  value       = module.api_location.public_ip
}

output "api_location_private_ip" {
  description = "Location API Private IP"
  value       = module.api_location.private_ip
}

# Phase 3: Extended APIs (2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# API-6: Image
output "api_image_instance_id" {
  description = "Image API Instance ID"
  value       = module.api_image.instance_id
}

output "api_image_public_ip" {
  description = "Image API Public IP"
  value       = module.api_image.public_ip
}

output "api_image_private_ip" {
  description = "Image API Private IP"
  value       = module.api_image.private_ip
}

# API-7: Chat
output "api_chat_instance_id" {
  description = "Chat API Instance ID"
  value       = module.api_chat.instance_id
}

output "api_chat_public_ip" {
  description = "Chat API Public IP"
  value       = module.api_chat.public_ip
}

output "api_chat_private_ip" {
  description = "Chat API Private IP"
  value       = module.api_chat.private_ip
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes Outputs (Phase 4: 2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Worker-1: Storage
output "worker_storage_instance_id" {
  description = "Worker Storage Instance ID"
  value       = module.worker_storage.instance_id
}

output "worker_storage_public_ip" {
  description = "Worker Storage Public IP"
  value       = module.worker_storage.public_ip
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes Outputs (Phase 4: 주석 처리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Worker-2: AI
output "worker_ai_instance_id" {
  description = "Worker AI Instance ID"
  value       = module.worker_ai.instance_id
}

output "worker_ai_public_ip" {
  description = "Worker AI Public IP"
  value       = module.worker_ai.public_ip
}

# output "worker_storage_private_ip" {
#   description = "Worker Storage Private IP"
#   value       = module.worker_storage.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure Nodes Outputs (Phase 1&2: PostgreSQL, Redis / Phase 4: RabbitMQ, Monitoring)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PostgreSQL (Phase 1)
output "postgresql_instance_id" {
  description = "PostgreSQL 노드 Instance ID"
  value       = module.postgresql.instance_id
}

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
output "redis_instance_id" {
  description = "Redis 노드 Instance ID"
  value       = module.redis.instance_id
}

output "redis_public_ip" {
  description = "Redis 노드 Public IP"
  value       = module.redis.public_ip
}

output "redis_private_ip" {
  description = "Redis 노드 Private IP"
  value       = module.redis.private_ip
}

# RabbitMQ (Phase 4: 2025-11-08 활성화)
output "rabbitmq_instance_id" {
  description = "RabbitMQ Instance ID"
  value       = module.rabbitmq.instance_id
}

output "rabbitmq_public_ip" {
  description = "RabbitMQ 노드 Public IP"
  value       = module.rabbitmq.public_ip
}

output "rabbitmq_private_ip" {
  description = "RabbitMQ 노드 Private IP"
  value       = module.rabbitmq.private_ip
}

# Monitoring (Phase 4: 2025-11-08 활성화)
output "monitoring_instance_id" {
  description = "Monitoring Instance ID"
  value       = module.monitoring.instance_id
}

output "monitoring_public_ip" {
  description = "Monitoring 노드 Public IP"
  value       = module.monitoring.public_ip
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 5: Network Nodes Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Ingress Gateway (Phase 5)
output "ingress_gateway_instance_id" {
  description = "Ingress Gateway Instance ID"
  value       = module.ingress_gateway.instance_id
}

output "ingress_gateway_public_ip" {
  description = "Ingress Gateway Public IP"
  value       = module.ingress_gateway.public_ip
}

# output "rabbitmq_private_ip" {
#   description = "RabbitMQ 노드 Private IP"
#   value       = module.rabbitmq.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ansible Inventory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ansible_inventory" {
  description = "Ansible Inventory 내용 (14-Node Architecture)"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_public_ip           = aws_eip.master.public_ip
    master_private_ip          = module.master.private_ip
    api_auth_public_ip         = module.api_auth.public_ip
    api_auth_private_ip        = module.api_auth.private_ip
    api_my_public_ip           = module.api_my.public_ip
    api_my_private_ip          = module.api_my.private_ip
    api_scan_public_ip         = module.api_scan.public_ip
    api_scan_private_ip        = module.api_scan.private_ip
    api_character_public_ip    = module.api_character.public_ip
    api_character_private_ip   = module.api_character.private_ip
    api_location_public_ip     = module.api_location.public_ip
    api_location_private_ip    = module.api_location.private_ip
    api_image_public_ip        = module.api_image.public_ip
    api_image_private_ip       = module.api_image.private_ip
    api_chat_public_ip         = module.api_chat.public_ip
    api_chat_private_ip        = module.api_chat.private_ip
    worker_storage_public_ip   = module.worker_storage.public_ip
    worker_storage_private_ip  = module.worker_storage.private_ip
    worker_ai_public_ip        = module.worker_ai.public_ip
    worker_ai_private_ip       = module.worker_ai.private_ip
    postgresql_public_ip       = module.postgresql.public_ip
    postgresql_private_ip      = module.postgresql.private_ip
    redis_public_ip            = module.redis.public_ip
    redis_private_ip           = module.redis.private_ip
    rabbitmq_public_ip         = module.rabbitmq.public_ip
    rabbitmq_private_ip        = module.rabbitmq.private_ip
    monitoring_public_ip       = module.monitoring.public_ip
    monitoring_private_ip      = module.monitoring.private_ip
    ingress_gateway_public_ip  = module.ingress_gateway.public_ip
    ingress_gateway_private_ip = module.ingress_gateway.private_ip
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSH Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ssh_commands" {
  description = "SSH 접속 명령어 (14-Node Architecture)"
  value = {
    master         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${aws_eip.master.public_ip}"
    api_auth       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_auth.public_ip}"
    api_my         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_my.public_ip}"
    api_scan       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_scan.public_ip}"
    api_character  = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_character.public_ip}"
    api_location   = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_location.public_ip}"
    api_image      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_image.public_ip}"
    api_chat       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_chat.public_ip}"
    worker_storage = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_storage.public_ip}"
    worker_ai      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_ai.public_ip}"
    postgresql     = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.postgresql.public_ip}"
    redis          = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis.public_ip}"
    rabbitmq       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.rabbitmq.public_ip}"
    monitoring     = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.monitoring.public_ip}"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cluster Info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "cluster_info" {
  description = "클러스터 정보 요약 (14-Node Architecture)"
  value = {
    vpc_id    = module.vpc.vpc_id
    master_ip = aws_eip.master.public_ip
    phase     = "Phase 1-4 Complete - 14-Node Full Production Architecture"
    api_ips = [
      module.api_auth.public_ip,
      module.api_my.public_ip,
      module.api_scan.public_ip,
      module.api_character.public_ip,
      module.api_location.public_ip,
      module.api_image.public_ip,
      module.api_chat.public_ip
    ]
    worker_ips = [
      module.worker_storage.public_ip,
      module.worker_ai.public_ip
    ]
    infra_ips = [
      module.postgresql.public_ip,
      module.redis.public_ip,
      module.rabbitmq.public_ip,
      module.monitoring.public_ip
    ]
    # 14-Node Architecture
    total_nodes        = 14  # Master + 7 APIs + 2 Workers + 4 Infra
    total_vcpu         = 32  # 2(master) + 7(APIs) + 4(workers) + 10(infra) + 4(monitoring)
    total_memory_gb    = 38  # 8(master) + 9(APIs) + 4(workers) + 8(infra) + 4(monitoring) + 4(psql) + 2(redis) + 1(rabbitmq)
    estimated_cost_usd = 245 # Monthly: t3.large*1 + t3.medium*2 + t3.small*5 + t3.micro*4
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Node Roles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "node_roles" {
  description = "노드별 역할 (14-Node Architecture)"
  value = {
    master         = "Control Plane (t3.large, 8GB) - Phase 1"
    api_auth       = "Authentication API (t3.micro, 1GB) - Phase 1"
    api_my         = "My Page API (t3.micro, 1GB) - Phase 1"
    api_scan       = "Waste Scan API (t3.small, 2GB) - Phase 2"
    api_character  = "Character & Mission API (t3.micro, 1GB) - Phase 2"
    api_location   = "Location & Map API (t3.micro, 1GB) - Phase 2"
    api_image      = "Image Delivery API (t3.micro, 1GB) - Phase 3"
    api_chat       = "Chat LLM API (t3.small, 2GB) - Phase 3"
    worker_storage = "Storage Worker - I/O Bound (t3.small, 2GB) - Phase 4"
    worker_ai      = "AI Worker - Network Bound (t3.small, 2GB) - Phase 4"
    postgresql     = "PostgreSQL - 7 Domain Schemas (t3.medium, 4GB) - Phase 1"
    redis          = "Redis Cache + JWT BlackList (t3.small, 2GB) - Phase 1"
    rabbitmq       = "RabbitMQ Message Queue (t3.small, 2GB) - Phase 4"
    monitoring     = "Prometheus + Grafana (t3.medium, 4GB) - Phase 4"
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
    api_base      = "https://api.${var.domain_name}"
    auth_url      = "https://api.${var.domain_name}/auth"
    my_url        = "https://api.${var.domain_name}/my"
    scan_url      = "https://api.${var.domain_name}/scan"
    character_url = "https://api.${var.domain_name}/character"
    location_url  = "https://api.${var.domain_name}/location"
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
  value = var.enable_cloudfront ? {
    distribution_id     = aws_cloudfront_distribution.images[0].id
    distribution_domain = aws_cloudfront_distribution.images[0].domain_name
    cdn_url             = "https://${aws_cloudfront_distribution.images[0].domain_name}"
    } : {
    distribution_id     = "CloudFront disabled"
    distribution_domain = "CloudFront disabled"
    cdn_url             = "CloudFront disabled - Use S3 direct URL"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Other Required Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "Public Subnet ID 목록"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private Subnet ID 목록"
  value       = module.vpc.private_subnet_ids
}

output "cluster_security_group_id" {
  description = "클러스터 노드 Security Group ID (master & worker 통합)"
  value       = module.security_groups.cluster_sg_id
}

output "alb_security_group_id" {
  description = "ALB용 Security Group ID"
  value       = module.security_groups.alb_sg_id
}

# 하위 호환성을 위한 별칭 (deprecated)
output "master_security_group_id" {
  description = "[DEPRECATED] Use cluster_security_group_id instead"
  value       = module.security_groups.cluster_sg_id
}

output "worker_security_group_id" {
  description = "[DEPRECATED] Use cluster_security_group_id instead"
  value       = module.security_groups.cluster_sg_id
}

output "aws_region" {
  description = "AWS Region"
  value       = var.aws_region
}

output "acm_certificate_arn" {
  description = "ACM Certificate ARN (domain_name이 설정된 경우)"
  value       = var.domain_name != "" ? try(aws_acm_certificate_validation.main[0].certificate_arn, aws_acm_certificate.main[0].arn, "") : ""
}
