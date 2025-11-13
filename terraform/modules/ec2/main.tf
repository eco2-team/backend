resource "aws_instance" "this" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.security_group_ids
  key_name               = var.key_name
  iam_instance_profile   = var.iam_instance_profile != "" ? var.iam_instance_profile : null

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = var.root_volume_type
    encrypted   = true

    tags = {
      Name = "${var.instance_name}-root"
    }
  }

  user_data = var.user_data

  tags = merge(
    {
      Name = var.instance_name
    },
    var.tags
  )

  lifecycle {
    ignore_changes = [user_data]
  }
}

