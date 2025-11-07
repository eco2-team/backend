# CloudFront CDN for S3 Images
# CDN + S3 기반 이미지 처리 아키텍처

# CloudFront Origin Access Identity (OAI)
resource "aws_cloudfront_origin_access_identity" "images" {
  comment = "OAI for ${var.environment}-${var.cluster_name} S3 images bucket"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "images" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CDN for waste analysis images - ${var.environment}"
  price_class         = "PriceClass_200"  # 아시아 + 북미 + 유럽
  
  # Origin: S3 Bucket
  origin {
    domain_name = aws_s3_bucket.images.bucket_regional_domain_name
    origin_id   = "S3-${aws_s3_bucket.images.id}"
    
    # OAI (Origin Access Identity) - S3 보안 연결
    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.images.cloudfront_access_identity_path
    }
  }
  
  # Default Cache Behavior
  default_cache_behavior {
    target_origin_id       = "S3-${aws_s3_bucket.images.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true
    
    # Cache Policy: Optimized for Images
    forwarded_values {
      query_string = false
      headers      = ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method"]
      
      cookies {
        forward = "none"
      }
    }
    
    # TTL 설정
    min_ttl     = 0
    default_ttl = 86400    # 24시간
    max_ttl     = 604800   # 7일 (분석 완료 후 이미지는 장기 캐싱)
  }
  
  # SSL Certificate (CloudFront는 us-east-1 인증서 필요)
  viewer_certificate {
    cloudfront_default_certificate = false
    acm_certificate_arn            = aws_acm_certificate.cdn.arn
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }
  
  # Custom Domain
  aliases = ["images.${var.domain_name}"]
  
  # Geo Restrictions (없음)
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  
  # Custom Error Responses
  custom_error_response {
    error_code            = 404
    error_caching_min_ttl = 10
  }
  
  custom_error_response {
    error_code            = 403
    error_caching_min_ttl = 10
  }
  
  tags = {
    Name        = "${var.environment}-images-cdn"
    Purpose     = "Image delivery optimization"
    Environment = var.environment
  }
}

# S3 Bucket Policy (CloudFront OAI만 액세스 허용)
resource "aws_s3_bucket_policy" "images_cdn" {
  bucket = aws_s3_bucket.images.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontOAI"
        Effect = "Allow"
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.images.iam_arn
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.images.arn}/*"
      }
    ]
  })
}

# ACM Certificate for CloudFront (us-east-1 필수!)
# CloudFront는 global 서비스이므로 us-east-1 리전의 인증서만 사용 가능
resource "aws_acm_certificate" "cdn" {
  provider          = aws.us_east_1
  domain_name       = "images.${var.domain_name}"
  validation_method = "DNS"
  
  lifecycle {
    create_before_destroy = true
  }
  
  tags = {
    Name        = "images.${var.domain_name}"
    Purpose     = "CloudFront CDN SSL"
    Environment = var.environment
  }
}

# ACM Certificate Validation
resource "aws_acm_certificate_validation" "cdn" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.cdn.arn
  validation_record_fqdns = [for record in aws_route53_record.cdn_cert_validation : record.fqdn]
}

# Route53 Record for ACM Validation
resource "aws_route53_record" "cdn_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cdn.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }
  
  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main[0].zone_id
}

# Route53 Record for CDN
resource "aws_route53_record" "cdn" {
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "images.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = aws_cloudfront_distribution.images.domain_name
    zone_id                = aws_cloudfront_distribution.images.hosted_zone_id
    evaluate_target_health = false
  }
}

# Outputs
output "cloudfront_distribution_id" {
  description = "CloudFront Distribution ID"
  value       = aws_cloudfront_distribution.images.id
}

output "cloudfront_domain_name" {
  description = "CloudFront Domain Name"
  value       = aws_cloudfront_distribution.images.domain_name
}

output "cdn_url" {
  description = "CDN URL for images"
  value       = "https://images.${var.domain_name}"
}

output "cdn_oai_iam_arn" {
  description = "CloudFront Origin Access Identity IAM ARN"
  value       = aws_cloudfront_origin_access_identity.images.iam_arn
}

