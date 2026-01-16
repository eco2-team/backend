[all:vars]
ansible_connection=ssh
ansible_user=ubuntu
ansible_ssh_private_key_file=~/.ssh/sesacthon.pem
ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
ansible_python_interpreter=/usr/bin/python3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Master Node (Control Plane)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[masters]
k8s-master ansible_host=${master_public_ip} private_ip=${master_private_ip} instance_type=t3.large

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Nodes (Phase 1&2: 7 nodes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[api_nodes]
k8s-api-auth ansible_host=${api_auth_public_ip} private_ip=${api_auth_private_ip} domain=auth instance_type=t3.micro phase=1
k8s-api-my ansible_host=${api_my_public_ip} private_ip=${api_my_private_ip} domain=my instance_type=t3.micro phase=1
k8s-api-scan ansible_host=${api_scan_public_ip} private_ip=${api_scan_private_ip} domain=scan instance_type=t3.small phase=2
k8s-api-character ansible_host=${api_character_public_ip} private_ip=${api_character_private_ip} domain=character instance_type=t3.micro phase=2
k8s-api-location ansible_host=${api_location_public_ip} private_ip=${api_location_private_ip} domain=location instance_type=t3.micro phase=2
k8s-api-image ansible_host=${api_image_public_ip} private_ip=${api_image_private_ip} domain=image instance_type=t3.micro phase=3
k8s-api-chat ansible_host=${api_chat_public_ip} private_ip=${api_chat_private_ip} domain=chat instance_type=t3.small phase=3
k8s-api-info ansible_host=${api_info_public_ip} private_ip=${api_info_private_ip} domain=info instance_type=t3.small phase=3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes (Phase 4: 2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[workers]
k8s-worker-storage ansible_host=${worker_storage_public_ip} private_ip=${worker_storage_private_ip} workload=worker-storage worker_type=io-bound domain=scan instance_type=t3.medium phase=4
k8s-worker-storage-2 ansible_host=${worker_storage_2_public_ip} private_ip=${worker_storage_2_private_ip} workload=worker-storage worker_type=io-bound domain=scan instance_type=t3.medium phase=4
k8s-worker-ai ansible_host=${worker_ai_public_ip} private_ip=${worker_ai_private_ip} workload=worker-ai worker_type=network-bound domain=scan,chat instance_type=t3.medium phase=4
k8s-worker-ai-2 ansible_host=${worker_ai_2_public_ip} private_ip=${worker_ai_2_private_ip} workload=worker-ai worker_type=network-bound domain=scan,chat instance_type=t3.medium phase=4

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure Nodes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PostgreSQL (Phase 1)
[postgresql]
k8s-postgresql ansible_host=${postgresql_public_ip} private_ip=${postgresql_private_ip} workload=database instance_type=t3.medium phase=1

# Redis (Phase 1) - 3-Node Cluster
[redis]
k8s-redis-auth ansible_host=${redis_auth_public_ip} private_ip=${redis_auth_private_ip} workload=cache redis_cluster=auth instance_type=t3.medium phase=1
k8s-redis-streams ansible_host=${redis_streams_public_ip} private_ip=${redis_streams_private_ip} workload=cache redis_cluster=streams instance_type=t3.small phase=1
k8s-redis-cache ansible_host=${redis_cache_public_ip} private_ip=${redis_cache_private_ip} workload=cache redis_cluster=cache instance_type=t3.small phase=1

# RabbitMQ (Phase 4: 2025-11-08 활성화)
[rabbitmq]
k8s-rabbitmq ansible_host=${rabbitmq_public_ip} private_ip=${rabbitmq_private_ip} workload=message-queue instance_type=t3.small phase=4

# Monitoring (Phase 4: 2025-11-08 활성화)
[monitoring]
k8s-monitoring ansible_host=${monitoring_public_ip} private_ip=${monitoring_private_ip} workload=monitoring instance_type=t3.large phase=4

# Logging (Phase 4: 2025-12 ELK Stack)
[logging]
k8s-logging ansible_host=${logging_public_ip} private_ip=${logging_private_ip} workload=logging instance_type=t3.large phase=4

# Ingress Gateway (Phase 5: Istio)
[ingress_gateway]
k8s-ingress-gateway ansible_host=${ingress_gateway_public_ip} private_ip=${ingress_gateway_private_ip} workload=gateway instance_type=t3.medium phase=5

# SSE Gateway (Phase 5: Pub/Sub Subscriber + Client Fan-out)
[sse_gateway]
k8s-sse-gateway ansible_host=${sse_gateway_public_ip} private_ip=${sse_gateway_private_ip} workload=sse instance_type=t3.small phase=5

# Event Router (Phase 6: Streams→Pub/Sub Bridge)
[event_router]
k8s-event-router ansible_host=${event_router_public_ip} private_ip=${event_router_private_ip} workload=event-router instance_type=t3.small phase=6

# Redis Pub/Sub (Phase 6: Realtime Broadcast)
[redis_pubsub]
k8s-redis-pubsub ansible_host=${redis_pubsub_public_ip} private_ip=${redis_pubsub_private_ip} workload=cache redis_cluster=pubsub instance_type=t3.small phase=6

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Group Definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[k8s_cluster:children]
masters
api_nodes
workers
postgresql
redis
redis_pubsub
rabbitmq
monitoring
logging
ingress_gateway
sse_gateway
event_router
