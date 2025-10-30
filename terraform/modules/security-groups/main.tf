resource "aws_security_group" "master" {
  name        = "${var.environment}-k8s-master-sg"
  description = "Security group for Kubernetes Master node"
  vpc_id      = var.vpc_id
  
  # SSH
  ingress {
    description = "SSH from allowed CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }
  
  # Kubernetes API Server
  ingress {
    description = "Kubernetes API"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # HTTP
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # HTTPS
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # etcd server client API
  ingress {
    description = "etcd"
    from_port   = 2379
    to_port     = 2380
    protocol    = "tcp"
    self        = true
  }
  
  # Kubelet API, kube-scheduler, kube-controller-manager
  ingress {
    description     = "Kubelet API"
    from_port       = 10250
    to_port         = 10252
    protocol        = "tcp"
    security_groups = [aws_security_group.worker.id]
  }
  
  # NodePort Services (선택)
  ingress {
    description = "NodePort Services"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  # Egress all
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "${var.environment}-k8s-master-sg"
  }
}

resource "aws_security_group" "worker" {
  name        = "${var.environment}-k8s-worker-sg"
  description = "Security group for Kubernetes Worker nodes"
  vpc_id      = var.vpc_id
  
  # SSH
  ingress {
    description = "SSH from allowed CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }
  
  # Kubelet API
  ingress {
    description     = "Kubelet API from master"
    from_port       = 10250
    to_port         = 10250
    protocol        = "tcp"
    security_groups = [aws_security_group.master.id]
  }
  
  # NodePort Services
  ingress {
    description     = "NodePort from master"
    from_port       = 30000
    to_port         = 32767
    protocol        = "tcp"
    security_groups = [aws_security_group.master.id]
  }
  
  # Worker 간 통신 (Pod network)
  ingress {
    description = "Worker to worker communication"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }
  
  # Master to Worker
  ingress {
    description     = "Master to worker"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.master.id]
  }
  
  # Egress all
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "${var.environment}-k8s-worker-sg"
  }
}

