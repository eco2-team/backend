# Route53 DNS Configuration

# Hosted Zone (도메인이 있는 경우)
# 도메인을 Route53에서 구매했거나 다른 곳에서 구매 후 NS 레코드를 Route53으로 변경한 경우

# 기존 Hosted Zone 사용 (도메인이 이미 있는 경우)
data "aws_route53_zone" "main" {
  count = var.domain_name != "" ? 1 : 0

  name         = var.domain_name
  private_zone = false
}

# 또는 새로 생성 (Route53에서 도메인 구매 시)
# resource "aws_route53_zone" "main" {
#   count = var.create_hosted_zone ? 1 : 0
#
#   name = var.domain_name
#
#   tags = {
#     Name = "${var.environment}-${var.cluster_name}-zone"
#   }
# }

# 이전 설정 (Master IP로 직접 연결) - 사용하지 않음
#
# # A 레코드: api.yourdomain.com → Master Public IP
# resource "aws_route53_record" "api" {
#   count = var.domain_name != "" ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = "api.${var.domain_name}"
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }
#
# # A 레코드: argocd.yourdomain.com → Master Public IP
# resource "aws_route53_record" "argocd" {
#   count = var.domain_name != "" ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = "argocd.${var.domain_name}"
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }
#
# # A 레코드: grafana.yourdomain.com → Master Public IP
# resource "aws_route53_record" "grafana" {
#   count = var.domain_name != "" ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = "grafana.${var.domain_name}"
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }
#
# # A 레코드: www.yourdomain.com → Master Public IP
# resource "aws_route53_record" "www" {
#   count = var.domain_name != "" ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = "www.${var.domain_name}"
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }
#
# # Apex 도메인 (growbin.app) → Master Public IP
# resource "aws_route53_record" "apex" {
#   count = var.domain_name != "" ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = var.domain_name
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }

# Wildcard A 레코드 (선택사항) - 사용하지 않음
# # *.yourdomain.com → Master Public IP
# resource "aws_route53_record" "wildcard" {
#   count = var.domain_name != "" && var.create_wildcard_record ? 1 : 0
#
#   zone_id = data.aws_route53_zone.main[0].zone_id
#   name    = "*.${var.domain_name}"
#   type    = "A"
#   ttl     = 300
#   records = [aws_eip.master.public_ip]
# }
