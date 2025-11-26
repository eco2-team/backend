locals {
  service_account_oidc_issuer_url = var.service_account_oidc_issuer_url != "" ? var.service_account_oidc_issuer_url : format("https://oidc.growbin.app/%s", var.environment)
  create_irsa                     = var.enable_irsa
}

data "tls_certificate" "service_account_oidc" {
  count = local.create_irsa ? 1 : 0
  url   = local.service_account_oidc_issuer_url
}

resource "aws_iam_openid_connect_provider" "cluster" {
  count = local.create_irsa ? 1 : 0
  url   = local.service_account_oidc_issuer_url

  client_id_list = [
    "sts.amazonaws.com"
  ]

  thumbprint_list = [
    data.tls_certificate.service_account_oidc[0].certificates[length(data.tls_certificate.service_account_oidc[0].certificates) - 1].sha1_fingerprint
  ]

  tags = {
    Name        = "${var.environment}-self-managed-oidc"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
