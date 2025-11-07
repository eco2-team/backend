[all:vars]
ansible_connection=aws_ssm
ansible_aws_ssm_bucket_name=
ansible_aws_ssm_region=ap-northeast-2
ansible_python_interpreter=/usr/bin/python3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master Node (Control Plane)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[masters]
k8s-master ansible_host=${master_instance_id} private_ip=${master_private_ip} instance_type=t3.large

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Nodes (Phase 1&2: 5 nodes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[api_nodes]
k8s-api-auth ansible_host=${api_auth_instance_id} private_ip=${api_auth_private_ip} domain=auth instance_type=t3.micro phase=1
k8s-api-my ansible_host=${api_my_instance_id} private_ip=${api_my_private_ip} domain=my instance_type=t3.micro phase=1
k8s-api-scan ansible_host=${api_scan_instance_id} private_ip=${api_scan_private_ip} domain=scan instance_type=t3.small phase=2
k8s-api-character ansible_host=${api_character_instance_id} private_ip=${api_character_private_ip} domain=character instance_type=t3.micro phase=2
k8s-api-location ansible_host=${api_location_instance_id} private_ip=${api_location_private_ip} domain=location instance_type=t3.micro phase=2

# Phase 3: Extended APIs (주석 처리)
# k8s-api-info ansible_host=TBD private_ip=TBD domain=info instance_type=t3.micro phase=3
# k8s-api-chat ansible_host=TBD private_ip=TBD domain=chat instance_type=t3.small phase=3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes (Phase 4: 주석 처리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[workers]
# k8s-worker-storage ansible_host=TBD private_ip=TBD workload=worker-storage worker_type=io-bound instance_type=t3.small phase=4
# k8s-worker-ai ansible_host=TBD private_ip=TBD workload=worker-ai worker_type=network-bound instance_type=t3.small phase=4

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure Nodes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PostgreSQL (Phase 1)
[postgresql]
k8s-postgresql ansible_host=${postgresql_instance_id} private_ip=${postgresql_private_ip} workload=database instance_type=t3.medium phase=1

# Redis (Phase 1)
[redis]
k8s-redis ansible_host=${redis_instance_id} private_ip=${redis_private_ip} workload=cache instance_type=t3.small phase=1

# RabbitMQ (Phase 4: 주석 처리)
[rabbitmq]
# k8s-rabbitmq ansible_host=TBD private_ip=TBD workload=message-queue instance_type=t3.small phase=4

# Monitoring (Phase 4: 주석 처리)
[monitoring]
# k8s-monitoring ansible_host=TBD private_ip=TBD workload=monitoring instance_type=t3.medium phase=4

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Group Definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[k8s_cluster:children]
masters
api_nodes
workers
postgresql
redis
rabbitmq
monitoring
