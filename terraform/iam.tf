# IAM Role for EC2 instances (AWS Session Manager)

# IAM Role
resource "aws_iam_role" "ec2_ssm_role" {
  name = "${var.environment}-k8s-ec2-ssm-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.environment}-k8s-ec2-ssm-role"
  }
}

# Attach AWS managed policy for Session Manager
resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.ec2_ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Attach AWS managed policy for CloudWatch (optional, for logging)
resource "aws_iam_role_policy_attachment" "cloudwatch_policy" {
  role       = aws_iam_role.ec2_ssm_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Instance Profile
resource "aws_iam_instance_profile" "k8s" {
  name = "${var.environment}-k8s-instance-profile"
  role = aws_iam_role.ec2_ssm_role.name

  tags = {
    Name = "${var.environment}-k8s-instance-profile"
  }
}

