output "master_public_ip" {
  description = "Master 노드 Public IP (Elastic IP)"
  value       = aws_eip.master.public_ip
}

output "master_private_ip" {
  description = "Master 노드 Private IP"
  value       = module.master.private_ip
}

output "api_waste_public_ip" {
  description = "Waste API Node Public IP"
  value       = module.api_waste.public_ip
}

output "api_waste_private_ip" {
  description = "Waste API Node Private IP"
  value       = module.api_waste.private_ip
}

output "api_auth_public_ip" {
  description = "Auth API Node Public IP"
  value       = module.api_auth.public_ip
}

output "api_auth_private_ip" {
  description = "Auth API Node Private IP"
  value       = module.api_auth.private_ip
}

output "api_userinfo_public_ip" {
  description = "Userinfo API Node Public IP"
  value       = module.api_userinfo.public_ip
}

output "api_userinfo_private_ip" {
  description = "Userinfo API Node Private IP"
  value       = module.api_userinfo.private_ip
}

output "api_location_public_ip" {
  description = "Location API Node Public IP"
  value       = module.api_location.public_ip
}

output "api_location_private_ip" {
  description = "Location API Node Private IP"
  value       = module.api_location.private_ip
}

output "api_recycle_info_public_ip" {
  description = "Recycle Info API Node Public IP"
  value       = module.api_recycle_info.public_ip
}

output "api_recycle_info_private_ip" {
  description = "Recycle Info API Node Private IP"
  value       = module.api_recycle_info.private_ip
}

output "api_chat_llm_public_ip" {
  description = "Chat LLM API Node Public IP"
  value       = module.api_chat_llm.public_ip
}

output "api_chat_llm_private_ip" {
  description = "Chat LLM API Node Private IP"
  value       = module.api_chat_llm.private_ip
}

output "worker_storage_public_ip" {
  description = "Worker Storage Node Public IP"
  value       = module.worker_storage.public_ip
}

output "worker_storage_private_ip" {
  description = "Worker Storage Node Private IP"
  value       = module.worker_storage.private_ip
}

output "worker_ai_public_ip" {
  description = "Worker AI Node Public IP"
  value       = module.worker_ai.public_ip
}

output "worker_ai_private_ip" {
  description = "Worker AI Node Private IP"
  value       = module.worker_ai.private_ip
}

output "ansible_inventory" {
  description = "Ansible Inventory 내용"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_public_ip             = aws_eip.master.public_ip
    master_private_ip            = module.master.private_ip
    api_waste_public_ip          = module.api_waste.public_ip
    api_waste_private_ip         = module.api_waste.private_ip
    api_auth_public_ip           = module.api_auth.public_ip
    api_auth_private_ip          = module.api_auth.private_ip
    api_userinfo_public_ip       = module.api_userinfo.public_ip
    api_userinfo_private_ip      = module.api_userinfo.private_ip
    api_location_public_ip       = module.api_location.public_ip
    api_location_private_ip      = module.api_location.private_ip
    api_recycle_info_public_ip   = module.api_recycle_info.public_ip
    api_recycle_info_private_ip  = module.api_recycle_info.private_ip
    api_chat_llm_public_ip       = module.api_chat_llm.public_ip
    api_chat_llm_private_ip      = module.api_chat_llm.private_ip
    worker_storage_public_ip     = module.worker_storage.public_ip
    worker_storage_private_ip    = module.worker_storage.private_ip
    worker_ai_public_ip          = module.worker_ai.public_ip
    worker_ai_private_ip         = module.worker_ai.private_ip
    rabbitmq_public_ip           = module.rabbitmq.public_ip
    rabbitmq_private_ip          = module.rabbitmq.private_ip
    postgresql_public_ip         = module.postgresql.public_ip
    postgresql_private_ip        = module.postgresql.private_ip
    redis_public_ip              = module.redis.public_ip
    redis_private_ip             = module.redis.private_ip
    monitoring_public_ip         = module.monitoring.public_ip
    monitoring_private_ip        = module.monitoring.private_ip
  })
}

output "ssh_commands" {
  description = "SSH 접속 명령어"
  value = {
    master            = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${aws_eip.master.public_ip}"
    api_waste         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_waste.public_ip}"
    api_auth          = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_auth.public_ip}"
    api_userinfo      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_userinfo.public_ip}"
    api_location      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_location.public_ip}"
    api_recycle_info  = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_recycle_info.public_ip}"
    api_chat_llm      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_chat_llm.public_ip}"
    worker_storage    = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_storage.public_ip}"
    worker_ai         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_ai.public_ip}"
    rabbitmq          = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.rabbitmq.public_ip}"
    postgresql        = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.postgresql.public_ip}"
    redis             = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis.public_ip}"
    monitoring        = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.monitoring.public_ip}"
  }
}

output "rabbitmq_public_ip" {
  description = "RabbitMQ 노드 Public IP"
  value       = module.rabbitmq.public_ip
}

output "rabbitmq_private_ip" {
  description = "RabbitMQ 노드 Private IP"
  value       = module.rabbitmq.private_ip
}

output "postgresql_public_ip" {
  description = "PostgreSQL 노드 Public IP"
  value       = module.postgresql.public_ip
}

output "postgresql_private_ip" {
  description = "PostgreSQL 노드 Private IP"
  value       = module.postgresql.private_ip
}

output "redis_public_ip" {
  description = "Redis 노드 Public IP"
  value       = module.redis.public_ip
}

output "redis_private_ip" {
  description = "Redis 노드 Private IP"
  value       = module.redis.private_ip
}

output "monitoring_public_ip" {
  description = "Monitoring 노드 Public IP"
  value       = module.monitoring.public_ip
}

output "monitoring_private_ip" {
  description = "Monitoring 노드 Private IP"
  value       = module.monitoring.private_ip
}

output "cluster_info" {
  description = "클러스터 정보 요약"
  value = {
    vpc_id             = module.vpc.vpc_id
    master_ip          = aws_eip.master.public_ip
    api_ips            = [
      module.api_waste.public_ip,
      module.api_auth.public_ip,
      module.api_userinfo.public_ip,
      module.api_location.public_ip,
      module.api_recycle_info.public_ip,
      module.api_chat_llm.public_ip
    ]
    worker_ips         = [module.worker_storage.public_ip, module.worker_ai.public_ip]
    rabbitmq_ip        = module.rabbitmq.public_ip
    postgresql_ip      = module.postgresql.public_ip
    redis_ip           = module.redis.public_ip
    monitoring_ip      = module.monitoring.public_ip
    total_nodes        = 13  # Master + API*6 + Worker*2 + Infra*4
    total_vcpu         = 18  # 2+1+1+1+1+1+1+2+2+2+2+2+2
    total_memory_gb    = 26  # 8+2+1+1+1+1+2+4+4+2+2+2+8
    estimated_cost_usd = 180  # t3.large*2 + t3.medium*2 + t3.small*4 + t3.micro*4
  }
}

output "node_roles" {
  description = "노드별 역할"
  value = {
    master              = "Control Plane (t3.large, 8GB)"
    api_waste           = "Waste API - 폐기물 분석 (t3.small, 2GB)"
    api_auth            = "Auth API - 인증/인가 (t3.micro, 1GB)"
    api_userinfo        = "Userinfo API - 사용자 정보 (t3.micro, 1GB)"
    api_location        = "Location API - 지도/위치 (t3.micro, 1GB)"
    api_recycle_info    = "Recycle Info API - 재활용 정보 (t3.micro, 1GB)"
    api_chat_llm        = "Chat LLM API - LLM 채팅 (t3.small, 2GB)"
    worker_storage      = "Celery Storage - image-uploader, rule-retriever, beat (t3.medium, 4GB)"
    worker_ai           = "Celery AI - gpt5-analyzer, response-generator (t3.medium, 4GB)"
    rabbitmq            = "RabbitMQ Message Queue (t3.small, 2GB)"
    postgresql          = "PostgreSQL Database (t3.small, 2GB)"
    redis               = "Redis Cache (t3.small, 2GB)"
    monitoring          = "Prometheus + Grafana (t3.large, 8GB)"
  }
}

output "dns_records" {
  description = "생성된 DNS 레코드 (domain_name 설정 시)"
  value = var.domain_name != "" ? {
    apex_domain = "https://${var.domain_name}"
    www_url     = "https://www.${var.domain_name}"
    api_url     = "https://api.${var.domain_name}"
    argocd_url  = "https://argocd.${var.domain_name}"
    grafana_url = "https://grafana.${var.domain_name}"
    wildcard    = var.create_wildcard_record ? "https://*.${var.domain_name}" : "disabled"
    nameservers = try(data.aws_route53_zone.main[0].name_servers, [])
  } : null
}


output "s3_bucket_info" {
  description = "S3 이미지 버킷 정보"
  value = {
    bucket_name = aws_s3_bucket.images.id
    bucket_arn  = aws_s3_bucket.images.arn
    region      = var.aws_region
  }
}

# ALB Controller 및 Ansible에서 필요한 Output
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
