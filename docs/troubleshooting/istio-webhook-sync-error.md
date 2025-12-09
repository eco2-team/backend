# Istio Webhook Sync Error 및 ArgoCD Drift 해결

## 1. 문제 상황

### 증상 1: ArgoCD Sync 실패
ArgoCD에서 `dev-istiod` 애플리케이션 Sync 시 다음과 같은 에러가 발생하며 실패함.

```
Failed to perform client-side apply migration: failed to perform client-side apply migration on manager kubectl-client-side-apply: error when patching "/dev/shm/...": validatingwebhookconfigurations.admissionregistration.k8s.io "istio-validator-istio-system" is invalid: metadata.resourceVersion: Invalid value: 0x0: must be specified for an update
```

### 증상 2: Istiod Webhook 연결 실패
Istiod 로그 또는 관련 에러에서 Webhook 호출 실패가 관측됨.
`istiod-default-validator`와 통신할 때 타임아웃 또는 연결 거부 발생 가능성.

## 2. 원인 분석

### 원인 1: Security Group 포트 차단 (15017)
Istio의 ValidatingWebhookConfiguration은 `istiod` 서비스의 443 포트로 요청을 보내지만, `istiod` 서비스는 이를 타겟 포트 **15017**로 포워딩함.
AWS Security Group 설정에서 Node 간 통신이 `self` 규칙으로 허용되어 있었으나, 명시적인 규칙 부재 혹은 특정 상황(Master 노드와 Worker 노드 간 통신 등)에서 Webhook 요청이 원활하지 않았을 수 있음. (혹은 명시적으로 허용하여 확실하게 보장할 필요가 있음)

### 원인 2: ArgoCD 리소스 업데이트 충돌
`metadata.resourceVersion: Invalid value: 0x0` 에러는 ArgoCD가 기존 리소스를 업데이트하려고 할 때, 클러스터에 존재하는 리소스 버전과 ArgoCD가 관리하는 상태 간의 충돌로 인해 발생. 특히 `ValidatingWebhookConfiguration`과 같이 쿠버네티스 컨트롤 플레인이 관여하는 리소스에서 Client-Side Apply에서 Server-Side Apply로 전환되거나 그 반대의 경우 충돌이 발생하기 쉬움.

## 3. 해결 방법

### 해결 1: Terraform Security Group 업데이트
`terraform/modules/security-groups/main.tf`에 Istio Webhook 포트(15017)를 허용하는 규칙을 명시적으로 추가함.

```hcl
# Istio Pilot Webhook Validation (Explicit Rule)
resource "aws_security_group_rule" "cluster_istio_webhook" {
  type              = "ingress"
  from_port         = 15017
  to_port           = 15017
  protocol          = "tcp"
  self              = true
  security_group_id = aws_security_group.k8s_cluster.id
  description       = "Istio Pilot Webhook Validation (15017)"
}
```

**적용 방법:**
```bash
terraform apply -var-file="env/dev.tfvars" -target="module.security_groups.aws_security_group_rule.cluster_istio_webhook"
```

### 해결 2: ArgoCD Sync Options 수정
`clusters/dev/apps/05-istio.yaml`에서 `dev-istiod` 애플리케이션에 `Replace=true` 옵션을 추가하여, 충돌 발생 시 리소스를 교체(삭제 후 재생성)하도록 설정함.

```yaml
    syncOptions:
    - CreateNamespace=true
    - ServerSideApply=true
    - Replace=true  # 추가됨
```

## 4. 결과
- Terraform 적용으로 15017 포트 통신이 보장됨.
- ArgoCD Sync 시 `Replace=true` 옵션 덕분에 버전 충돌 없이 정상적으로 동기화됨.
