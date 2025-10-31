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
    master_public_ip   = aws_eip.master.public_ip
    master_private_ip  = module.master.private_ip
    worker_1_public_ip = module.worker_1.public_ip
    worker_1_private_ip = module.worker_1.private_ip
    worker_2_public_ip = module.worker_2.public_ip
    worker_2_private_ip = module.worker_2.private_ip
  })
}

output "ssh_commands" {
  description = "SSH 접속 명령어"
  value = {
    master   = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${aws_eip.master.public_ip}"
    worker_1 = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_1.public_ip}"
    worker_2 = "ssh -i ~/.ssh/sesacthon.pem ubuntu@${module.worker_2.public_ip}"
  }
}

output "cluster_info" {
  description = "클러스터 정보 요약"
  value = {
    vpc_id             = module.vpc.vpc_id
    master_ip          = aws_eip.master.public_ip
    worker_ips         = [module.worker_1.public_ip, module.worker_2.public_ip]
    total_nodes        = 3
    total_vcpu         = 6
    total_memory_gb    = 10
    estimated_cost_usd = 105
  }
}

output "dns_records" {
  description = "생성된 DNS 레코드 (domain_name 설정 시)"
  value = var.domain_name != "" ? {
    api_url     = "https://api.${var.domain_name}"
    argocd_url  = "https://argocd.${var.domain_name}"
    grafana_url = "https://grafana.${var.domain_name}"
    nameservers = try(data.aws_route53_zone.main[0].name_servers, [])
  } : null
}

