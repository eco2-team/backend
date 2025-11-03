# S3 Bucket for Image Storage
# 프론트엔드 직접 업로드 + 백엔드는 URL만 읽기

resource "aws_s3_bucket" "images" {
  bucket = "${var.environment}-${var.cluster_name}-images"

  tags = {
    Name        = "${var.environment}-${var.cluster_name}-images"
    Purpose     = "AI 분석용 이미지 저장"
    Environment = var.environment
  }
}

# Versioning (선택사항, 데이터 보호)
resource "aws_s3_bucket_versioning" "images" {
  bucket = aws_s3_bucket.images.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Lifecycle (30일 후 IA, 90일 후 삭제)
resource "aws_s3_bucket_lifecycle_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    id     = "cleanup-old-images"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"  # Infrequent Access
    }

    expiration {
      days = 90  # 90일 후 자동 삭제
    }
  }
}

# CORS (프론트엔드 직접 업로드용)
resource "aws_s3_bucket_cors_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = [
      "https://${var.domain_name}",
      "https://www.${var.domain_name}",
      "http://localhost:3000",  # 개발용
      "http://localhost:5173"   # Vite 개발 서버
    ]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Public Access Block (보안)
resource "aws_s3_bucket_public_access_block" "images" {
  bucket = aws_s3_bucket.images.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Encryption (기본 암호화)
resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# IAM Policy for Pre-signed URL (Backend용)
resource "aws_iam_policy" "s3_presigned_url" {
  name        = "${var.environment}-s3-presigned-url-policy"
  description = "S3 Pre-signed URL 생성 권한 (Backend)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.images.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.images.arn
      }
    ]
  })

  tags = {
    Name = "${var.environment}-s3-presigned-url-policy"
  }
}

# IAM Role에 S3 Policy 추가 (EC2 Instance Profile)
resource "aws_iam_role_policy_attachment" "s3_backend" {
  role       = aws_iam_role.ec2_ssm_role.name
  policy_arn = aws_iam_policy.s3_presigned_url.arn
}

