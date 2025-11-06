[all:vars]
ansible_user=ubuntu
ansible_ssh_private_key_file=~/.ssh/sesacthon
ansible_python_interpreter=/usr/bin/python3

[masters]
k8s-master ansible_host=${master_public_ip} private_ip=${master_private_ip}

[api_nodes]
k8s-api-waste ansible_host=${api_waste_public_ip} private_ip=${api_waste_private_ip} workload=api instance_type=t3.small service=waste replicas=3
k8s-api-auth ansible_host=${api_auth_public_ip} private_ip=${api_auth_private_ip} workload=api instance_type=t3.micro service=auth replicas=2
k8s-api-userinfo ansible_host=${api_userinfo_public_ip} private_ip=${api_userinfo_private_ip} workload=api instance_type=t3.micro service=userinfo replicas=2
k8s-api-location ansible_host=${api_location_public_ip} private_ip=${api_location_private_ip} workload=api instance_type=t3.micro service=location replicas=2
k8s-api-recycle-info ansible_host=${api_recycle_info_public_ip} private_ip=${api_recycle_info_private_ip} workload=api instance_type=t3.micro service=recycle-info replicas=2
k8s-api-chat-llm ansible_host=${api_chat_llm_public_ip} private_ip=${api_chat_llm_private_ip} workload=api instance_type=t3.small service=chat-llm replicas=3

[workers]
k8s-worker-storage ansible_host=${worker_storage_public_ip} private_ip=${worker_storage_private_ip} workload=async-workers instance_type=t3.medium workers="image-uploader,rule-retriever,task-scheduler" type=storage
k8s-worker-ai ansible_host=${worker_ai_public_ip} private_ip=${worker_ai_private_ip} workload=async-workers instance_type=t3.medium workers="gpt5-analyzer,response-generator" type=ai

[rabbitmq]
k8s-rabbitmq ansible_host=${rabbitmq_public_ip} private_ip=${rabbitmq_private_ip} workload=message-queue instance_type=t3.small

[postgresql]
k8s-postgresql ansible_host=${postgresql_public_ip} private_ip=${postgresql_private_ip} workload=database instance_type=t3.small

[redis]
k8s-redis ansible_host=${redis_public_ip} private_ip=${redis_private_ip} workload=cache instance_type=t3.small

[monitoring]
k8s-monitoring ansible_host=${monitoring_public_ip} private_ip=${monitoring_private_ip} workload=monitoring instance_type=t3.large

[k8s_cluster:children]
masters
api_nodes
workers
rabbitmq
postgresql
redis
monitoring
