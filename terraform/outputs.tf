# VPC ID (ALB Controller용)
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

# ACM Certificate ARN (ALB SSL/TLS용)
output "acm_certificate_arn" {
  description = "ACM Certificate ARN"
  value       = try(aws_acm_certificate.main[0].arn, "")
}

output "master_public_ip" {
  description = "Master 노드 Public IP (Elastic IP)"
  value       = aws_eip.master.public_ip
}

output "master_private_ip" {
  description = "Master 노드 Private IP"
  value       = module.master.private_ip
}

output "worker_1_public_ip" {
  description = "Worker 1 Public IP"
  value       = module.worker_1.public_ip
}

output "worker_1_private_ip" {
  description = "Worker 1 Private IP"
  value       = module.worker_1.private_ip
}

output "worker_2_public_ip" {
  description = "Worker 2 Public IP"
  value       = module.worker_2.public_ip
}

output "worker_2_private_ip" {
  description = "Worker 2 Private IP"
  value       = module.worker_2.private_ip
}

output "ansible_inventory" {
  description = "Ansible Inventory 내용"
  value = templatefile("${path.module}/templates/hosts.tpl", {
    master_public_ip    = aws_eip.master.public_ip
    master_private_ip   = module.master.private_ip
    worker_1_public_ip  = module.worker_1.public_ip
    worker_1_private_ip = module.worker_1.private_ip
    worker_2_public_ip  = module.worker_2.public_ip
    worker_2_private_ip = module.worker_2.private_ip
    storage_public_ip   = module.storage.public_ip
    storage_private_ip  = module.storage.private_ip
  })
}

output "ssh_commands" {
  description = "SSH 접속 명령어"
  value = {
    master   = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${aws_eip.master.public_ip}"
    worker_1 = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_1.public_ip}"
    worker_2 = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_2.public_ip}"
    storage  = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.storage.public_ip}"
  }
}

output "storage_public_ip" {
  description = "Storage 노드 Public IP"
  value       = module.storage.public_ip
}

output "storage_private_ip" {
  description = "Storage 노드 Private IP"
  value       = module.storage.private_ip
}

output "cluster_info" {
  description = "클러스터 정보 요약"
  value = {
    vpc_id             = module.vpc.vpc_id
    master_ip          = aws_eip.master.public_ip
    worker_ips         = [module.worker_1.public_ip, module.worker_2.public_ip]
    storage_ip         = module.storage.public_ip
    total_nodes        = 4
    total_vcpu         = 8  # 2+2+2+2
    total_memory_gb    = 24  # 8+4+4+8
    estimated_cost_usd = 180
  }
}

output "node_roles" {
  description = "노드별 역할 (4-Tier Layered Architecture)"
  value = {
    master   = "Tier 1: Control Plane (kube-apiserver, etcd, Prometheus, ArgoCD) - t3.large, 8GB"
    worker_1 = "Tier 2: Data Plane Sync API (auth, users, locations) - t3.medium, 4GB"
    worker_2 = "Tier 2: Data Plane Async (waste, AI Workers, Batch Workers) - t3.medium, 4GB"
    storage  = "Tier 3+4: MQ (RabbitMQ HA ×3) + Storage (PostgreSQL, Redis) - t3.large, 8GB"
  }
}

output "tier_architecture" {
  description = "4-Tier Layered Architecture"
  value = {
    tier_1 = "Control Plane (Orchestration) - Master"
    tier_2 = "Data Plane (Business Logic, Sync + Async) - Worker-1 + Worker-2"
    tier_3 = "Message Queue (Middleware, RabbitMQ HA) - Storage"
    tier_4 = "Persistence (PostgreSQL + Redis Cache) - Storage"
    note   = "Storage 노드 = Tier 3 (MQ) + Tier 4 (DB) 논리적 분리"
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
