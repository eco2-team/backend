output "master_sg_id" {
  description = "Master 보안 그룹 ID"
  value       = aws_security_group.master.id
}

output "worker_sg_id" {
  description = "Worker 보안 그룹 ID"
  value       = aws_security_group.worker.id
}

