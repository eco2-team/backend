terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "SeSACTHON"
      ManagedBy   = "Terraform"
      Environment = var.environment
      Team        = "Backend"
    }
  }
}

# CloudFront requires ACM certificate in us-east-1
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  
  default_tags {
    tags = {
      Project     = "SeSACTHON"
      ManagedBy   = "Terraform"
      Environment = var.environment
      Team        = "Backend"
    }
  }
}

# Data Sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"
  
  vpc_cidr    = var.vpc_cidr
  environment = var.environment
  azs         = data.aws_availability_zones.available.names
}

# Security Groups Module
module "security_groups" {
  source = "./modules/security-groups"
  
  vpc_id           = module.vpc.vpc_id
  allowed_ssh_cidr = var.allowed_ssh_cidr
  environment      = var.environment
}

# SSH Key Pair
resource "aws_key_pair" "k8s" {
  key_name   = "k8s-cluster-key"
  public_key = file(var.public_key_path)
  
  tags = {
    Name = "k8s-cluster-key"
  }
}

# EC2 Instances - Master (Control Plane + Monitoring)
module "master" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-master"
  instance_type         = "t3.large"  # 8GB (Control Plane + Prometheus)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.master_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 80  # Prometheus TSDB
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-master"
  })
  
  tags = {
    Role = "control-plane"
  }
}

# EC2 Instances - API Nodes (6 nodes)
# API-1: Waste Analysis (High Traffic)
module "api_waste" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-waste"
  instance_type         = "t3.small"  # 2GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-waste"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-waste"
    Domain   = "waste"
  }
}

# API-2: Authentication & Authorization
module "api_auth" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-auth"
  instance_type         = "t3.micro"  # 1GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-auth"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-auth"
    Domain   = "auth"
  }
}

# API-3: User Information
module "api_userinfo" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-userinfo"
  instance_type         = "t3.micro"  # 1GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-userinfo"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-userinfo"
    Domain   = "userinfo"
  }
}

# API-4: Location & Map
module "api_location" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-location"
  instance_type         = "t3.micro"  # 1GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-location"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-location"
    Domain   = "location"
  }
}

# API-5: Recycle Information
module "api_recycle_info" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-recycle-info"
  instance_type         = "t3.micro"  # 1GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-recycle-info"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-recycle-info"
    Domain   = "recycle-info"
  }
}

# API-6: Chat LLM
module "api_chat_llm" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-chat-llm"
  instance_type         = "t3.small"  # 2GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-chat-llm"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api-chat-llm"
    Domain   = "chat-llm"
  }
}

# Worker Nodes (2 nodes)
# Worker-1: Storage & I/O Operations
module "worker_storage" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-storage"
  instance_type         = "t3.medium"  # 4GB (I/O Bound - Eventlet Pool)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # Image uploads + Local WAL
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-storage"
  })
  
  tags = {
    Role     = "worker"
    Workload = "worker-storage"
    Type     = "io-bound"
  }
}

# Worker-2: AI Processing
module "worker_ai" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-ai"
  instance_type         = "t3.medium"  # 4GB (Network Bound - Prefork Pool)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # AI models + GPT cache + Local WAL
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-ai"
  })
  
  tags = {
    Role     = "worker"
    Workload = "worker-ai"
    Type     = "network-bound"
  }
}

# EC2 Instances - RabbitMQ (Message Queue)
module "rabbitmq" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-rabbitmq"
  instance_type         = "t3.small"  # 2GB (RabbitMQ only)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]  # Same AZ as Master
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # RabbitMQ data
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-rabbitmq"
  })
  
  tags = {
    Role     = "worker"
    Workload = "message-queue"
  }
}

# EC2 Instances - PostgreSQL (Database - 도메인별 DB 분리)
module "postgresql" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-postgresql"
  instance_type         = "t3.medium"  # 4GB (도메인별 DB: auth, waste, chat, location, analytics)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]  # Different AZ
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 80  # PostgreSQL data (5 domains)
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-postgresql"
  })
  
  tags = {
    Role     = "worker"
    Workload = "database"
  }
}

# EC2 Instances - Redis (Cache)
module "redis" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-redis"
  instance_type         = "t3.small"  # 2GB (Redis only)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]  # Different AZ
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30  # Redis data (mostly in-memory)
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-redis"
  })
  
  tags = {
    Role     = "worker"
    Workload = "cache"
  }
}

# EC2 Instances - Monitoring (Prometheus + Grafana)
module "monitoring" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-monitoring"
  instance_type         = "t3.large"  # 8GB (Prometheus + Grafana) - Upgraded for CPU
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]  # Same AZ as Worker-1
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 60  # Prometheus TSDB + Grafana
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-monitoring"
  })
  
  tags = {
    Role     = "worker"
    Workload = "monitoring"
  }
}

# Elastic IP for Master
resource "aws_eip" "master" {
  instance = module.master.instance_id
  domain   = "vpc"
  
  tags = {
    Name = "k8s-master-eip"
  }
}

