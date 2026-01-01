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

# Worker-3: Storage (확장)
output "worker_storage_2_instance_id" {
  description = "Worker Storage 2 Instance ID"
  value       = module.worker_storage_2.instance_id
}

output "worker_storage_2_public_ip" {
  description = "Worker Storage 2 Public IP"
  value       = module.worker_storage_2.public_ip
}

# Worker-4: AI (확장)
output "worker_ai_2_instance_id" {
  description = "Worker AI 2 Instance ID"
  value       = module.worker_ai_2.instance_id
}

output "worker_ai_2_public_ip" {
  description = "Worker AI 2 Public IP"
  value       = module.worker_ai_2.public_ip
}

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

# Redis Auth (Phase 1) - Blacklist + OAuth
output "redis_auth_instance_id" {
  description = "Redis Auth Instance ID"
  value       = module.redis_auth.instance_id
}

output "redis_auth_public_ip" {
  description = "Redis Auth Public IP"
  value       = module.redis_auth.public_ip
}

output "redis_auth_private_ip" {
  description = "Redis Auth Private IP"
  value       = module.redis_auth.private_ip
}

# Redis Streams (Phase 1) - SSE Events
output "redis_streams_instance_id" {
  description = "Redis Streams Instance ID"
  value       = module.redis_streams.instance_id
}

output "redis_streams_public_ip" {
  description = "Redis Streams Public IP"
  value       = module.redis_streams.public_ip
}

output "redis_streams_private_ip" {
  description = "Redis Streams Private IP"
  value       = module.redis_streams.private_ip
}

# Redis Cache (Phase 1) - Celery + Domain Cache
output "redis_cache_instance_id" {
  description = "Redis Cache Instance ID"
  value       = module.redis_cache.instance_id
}

output "redis_cache_public_ip" {
  description = "Redis Cache Public IP"
  value       = module.redis_cache.public_ip
}

output "redis_cache_private_ip" {
  description = "Redis Cache Private IP"
  value       = module.redis_cache.private_ip
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

# Logging (Phase 4: 2025-12 ELK Stack)
output "logging_instance_id" {
  description = "Logging (ELK) Instance ID"
  value       = module.logging.instance_id
}

output "logging_public_ip" {
  description = "Logging (ELK) 노드 Public IP"
  value       = module.logging.public_ip
}

output "logging_private_ip" {
  description = "Logging (ELK) 노드 Private IP"
  value       = module.logging.private_ip
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

# SSE Gateway (Phase 5)
output "sse_gateway_instance_id" {
  description = "SSE Gateway Instance ID"
  value       = module.sse_gateway.instance_id
}

output "sse_gateway_public_ip" {
  description = "SSE Gateway Public IP"
  value       = module.sse_gateway.public_ip
}

output "sse_gateway_private_ip" {
  description = "SSE Gateway Private IP"
  value       = module.sse_gateway.private_ip
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 6: HA Event Architecture Outputs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Event Router (Phase 6)
output "event_router_instance_id" {
  description = "Event Router Instance ID"
  value       = module.event_router.instance_id
}

output "event_router_public_ip" {
  description = "Event Router Public IP"
  value       = module.event_router.public_ip
}

output "event_router_private_ip" {
  description = "Event Router Private IP"
  value       = module.event_router.private_ip
}

# Redis Pub/Sub (Phase 6)
output "redis_pubsub_instance_id" {
  description = "Redis Pub/Sub Instance ID"
  value       = module.redis_pubsub.instance_id
}

output "redis_pubsub_public_ip" {
  description = "Redis Pub/Sub Public IP"
  value       = module.redis_pubsub.public_ip
}

output "redis_pubsub_private_ip" {
  description = "Redis Pub/Sub Private IP"
  value       = module.redis_pubsub.private_ip
}

# output "rabbitmq_private_ip" {
#   description = "RabbitMQ 노드 Private IP"
#   value       = module.rabbitmq.private_ip
# }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ansible Inventory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ansible_inventory" {
  description = "Ansible Inventory 내용 (20-Node Architecture)"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_public_ip            = aws_eip.master.public_ip
    master_private_ip           = module.master.private_ip
    api_auth_public_ip          = module.api_auth.public_ip
    api_auth_private_ip         = module.api_auth.private_ip
    api_my_public_ip            = module.api_my.public_ip
    api_my_private_ip           = module.api_my.private_ip
    api_scan_public_ip          = module.api_scan.public_ip
    api_scan_private_ip         = module.api_scan.private_ip
    api_character_public_ip     = module.api_character.public_ip
    api_character_private_ip    = module.api_character.private_ip
    api_location_public_ip      = module.api_location.public_ip
    api_location_private_ip     = module.api_location.private_ip
    api_image_public_ip         = module.api_image.public_ip
    api_image_private_ip        = module.api_image.private_ip
    api_chat_public_ip          = module.api_chat.public_ip
    api_chat_private_ip         = module.api_chat.private_ip
    worker_storage_public_ip    = module.worker_storage.public_ip
    worker_storage_private_ip   = module.worker_storage.private_ip
    worker_ai_public_ip         = module.worker_ai.public_ip
    worker_ai_private_ip        = module.worker_ai.private_ip
    worker_storage_2_public_ip  = module.worker_storage_2.public_ip
    worker_storage_2_private_ip = module.worker_storage_2.private_ip
    worker_ai_2_public_ip       = module.worker_ai_2.public_ip
    worker_ai_2_private_ip      = module.worker_ai_2.private_ip
    postgresql_public_ip        = module.postgresql.public_ip
    postgresql_private_ip       = module.postgresql.private_ip
    redis_auth_public_ip        = module.redis_auth.public_ip
    redis_auth_private_ip       = module.redis_auth.private_ip
    redis_streams_public_ip     = module.redis_streams.public_ip
    redis_streams_private_ip    = module.redis_streams.private_ip
    redis_cache_public_ip       = module.redis_cache.public_ip
    redis_cache_private_ip      = module.redis_cache.private_ip
    rabbitmq_public_ip          = module.rabbitmq.public_ip
    rabbitmq_private_ip         = module.rabbitmq.private_ip
    monitoring_public_ip        = module.monitoring.public_ip
    monitoring_private_ip       = module.monitoring.private_ip
    logging_public_ip           = module.logging.public_ip
    logging_private_ip          = module.logging.private_ip
    ingress_gateway_public_ip   = module.ingress_gateway.public_ip
    ingress_gateway_private_ip  = module.ingress_gateway.private_ip
    sse_gateway_public_ip       = module.sse_gateway.public_ip
    sse_gateway_private_ip      = module.sse_gateway.private_ip
    event_router_public_ip      = module.event_router.public_ip
    event_router_private_ip     = module.event_router.private_ip
    redis_pubsub_public_ip      = module.redis_pubsub.public_ip
    redis_pubsub_private_ip     = module.redis_pubsub.private_ip
  })
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSH Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "ssh_commands" {
  description = "SSH 접속 명령어 (20-Node Architecture)"
  value = {
    master           = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${aws_eip.master.public_ip}"
    api_auth         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_auth.public_ip}"
    api_my           = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_my.public_ip}"
    api_scan         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_scan.public_ip}"
    api_character    = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_character.public_ip}"
    api_location     = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_location.public_ip}"
    api_image        = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_image.public_ip}"
    api_chat         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.api_chat.public_ip}"
    worker_storage   = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_storage.public_ip}"
    worker_storage_2 = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_storage_2.public_ip}"
    worker_ai        = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_ai.public_ip}"
    worker_ai_2      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_ai_2.public_ip}"
    postgresql       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.postgresql.public_ip}"
    redis_auth       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis_auth.public_ip}"
    redis_streams    = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis_streams.public_ip}"
    redis_cache      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis_cache.public_ip}"
    rabbitmq         = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.rabbitmq.public_ip}"
    monitoring       = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.monitoring.public_ip}"
    logging          = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.logging.public_ip}"
    sse_gateway      = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.sse_gateway.public_ip}"
    event_router     = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.event_router.public_ip}"
    redis_pubsub     = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.redis_pubsub.public_ip}"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cluster Info
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "cluster_info" {
  description = "클러스터 정보 요약 (20-Node Architecture)"
  value = {
    vpc_id    = module.vpc.vpc_id
    master_ip = aws_eip.master.public_ip
    phase     = "Phase 1-6 Complete - 20-Node HA Architecture"
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
      module.worker_storage_2.public_ip,
      module.worker_ai.public_ip,
      module.worker_ai_2.public_ip
    ]
    infra_ips = [
      module.postgresql.public_ip,
      module.redis_auth.public_ip,
      module.redis_streams.public_ip,
      module.redis_cache.public_ip,
      module.redis_pubsub.public_ip,
      module.rabbitmq.public_ip,
      module.monitoring.public_ip,
      module.logging.public_ip
    ]
    gateway_ips = [
      module.ingress_gateway.public_ip,
      module.sse_gateway.public_ip,
      module.event_router.public_ip
    ]
    # 20-Node Architecture (Phase 6: HA Event)
    total_nodes        = 20  # Master + 7 APIs + 2 Workers + 8 Infra + 3 Gateway
    total_vcpu         = 44  # +4 (event-router t3.small + redis-pubsub t3.small)
    total_memory_gb    = 60  # +4 (2GB + 2GB)
    estimated_cost_usd = 380 # +30 (t3.small × 2)
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Node Roles
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

output "node_roles" {
  description = "노드별 역할 (20-Node Architecture)"
  value = {
    master           = "Control Plane (t3.xlarge, 16GB) - Phase 0"
    api_auth         = "Authentication API (t3.small, 2GB) - Phase 1"
    api_my           = "My Page API (t3.small, 2GB) - Phase 1"
    api_scan         = "Waste Scan API (t3.medium, 4GB) - Phase 2"
    api_character    = "Character & Mission API (t3.small, 2GB) - Phase 2"
    api_location     = "Location & Map API (t3.small, 2GB) - Phase 2"
    api_image        = "Image Delivery API (t3.small, 2GB) - Phase 3"
    api_chat         = "Chat LLM API (t3.medium, 4GB) - Phase 3"
    worker_storage   = "Storage Worker - I/O Bound (t3.medium, 4GB) - Phase 4"
    worker_storage_2 = "Storage Worker 2 - I/O Bound (t3.medium, 4GB) - Phase 4"
    worker_ai        = "AI Worker - Network Bound (t3.medium, 4GB) - Phase 4"
    worker_ai_2      = "AI Worker 2 - Network Bound (t3.medium, 4GB) - Phase 4"
    postgresql       = "PostgreSQL - 7 Domain Schemas (t3.large, 8GB) - Phase 1"
    redis_auth       = "Redis Auth - Blacklist + OAuth (t3.medium, 4GB) - Phase 1"
    redis_streams    = "Redis Streams - SSE Events (t3.small, 2GB) - Phase 1"
    redis_cache      = "Redis Cache - Celery + Domain (t3.small, 2GB) - Phase 1"
    redis_pubsub     = "Redis Pub/Sub - Realtime Broadcast (t3.small, 2GB) - Phase 6"
    rabbitmq         = "RabbitMQ Message Queue (t3.medium, 4GB) - Phase 4"
    monitoring       = "Prometheus + Grafana (t3.large, 8GB) - Phase 4"
    logging          = "ELK Stack - Elasticsearch + Logstash + Kibana (t3.large, 8GB) - Phase 4"
    ingress_gateway  = "Istio Ingress Gateway (t3.medium, 4GB) - Phase 5"
    sse_gateway      = "SSE Pub/Sub Subscriber + Client Fan-out (t3.small, 2GB) - Phase 5"
    event_router     = "Event Router - Streams→Pub/Sub Bridge (t3.small, 2GB) - Phase 6"
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
