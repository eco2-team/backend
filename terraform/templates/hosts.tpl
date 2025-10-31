[all:vars]
ansible_user=ubuntu
ansible_ssh_private_key_file=~/.ssh/sesacthon
ansible_python_interpreter=/usr/bin/python3

[masters]
k8s-master ansible_host=${master_public_ip} private_ip=${master_private_ip}

[workers]
k8s-worker-1 ansible_host=${worker_1_public_ip} private_ip=${worker_1_private_ip} workload=cpu instance_type=t3.medium
k8s-worker-2 ansible_host=${worker_2_public_ip} private_ip=${worker_2_private_ip} workload=network instance_type=t3.small

[k8s_cluster:children]
masters
workers

