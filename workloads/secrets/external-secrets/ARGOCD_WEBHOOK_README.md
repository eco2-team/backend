# ArgoCD Webhook Secret Configuration

이 디렉토리는 ArgoCD webhook secret 설정을 위한 매니페스트를 포함합니다.

## Webhook Secret 관리

ArgoCD webhook secret은 **External Secrets Operator**를 통해 AWS SSM Parameter Store에서 자동으로 주입됩니다.

### AWS SSM Parameter Store

다음 경로에 webhook secret을 저장해야 합니다:

```bash
# Dev 환경
aws ssm put-parameter \
  --name "/sesacthon/dev/argocd/webhook-github-secret" \
  --value "j51q8MvvksWL9QsqRldhTPOK2BkcyCQfIkF/IKXE0Hc=" \
  --type SecureString \
  --region ap-northeast-2

# Prod 환경
aws ssm put-parameter \
  --name "/sesacthon/prod/argocd/webhook-github-secret" \
  --value "YOUR_PROD_SECRET_HERE" \
  --type SecureString \
  --region ap-northeast-2
```

### External Secret

External Secret은 다음 경로에 정의되어 있습니다:
- Dev: `workloads/secrets/external-secrets/dev/argocd-webhook-secret.yaml`
- Prod: `workloads/secrets/external-secrets/prod/argocd-webhook-secret.yaml`

### ArgoCD ConfigMap 참조

ArgoCD server는 다음 설정으로 webhook secret을 참조합니다:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-cm
  namespace: argocd
data:
  webhook.github.secret: |
    $argocd-webhook-secret:webhook.github.secret
```

이렇게 하면 External Secret이 생성한 Secret의 값을 참조합니다.

### GitHub Webhook 설정

GitHub Repository Settings에서 webhook을 설정할 때:

1. **Payload URL**: `https://argocd.dev.growbin.app/api/v1/webhook`
2. **Content type**: `application/json`
3. **Secret**: AWS SSM에 저장된 것과 동일한 값 입력
4. **Events**: `Push events`

### 확인 방법

```bash
# External Secret 상태 확인
kubectl get externalsecret -n argocd argocd-webhook-secret

# 생성된 Secret 확인
kubectl get secret -n argocd argocd-webhook-secret

# Secret 값 확인 (base64 디코딩)
kubectl get secret -n argocd argocd-webhook-secret -o jsonpath='{.data.webhook\.github\.secret}' | base64 -d
```

### 생성된 Secret 값 (Dev)

```
j51q8MvvksWL9QsqRldhTPOK2BkcyCQfIkF/IKXE0Hc=
```

이 값을 AWS SSM과 GitHub webhook 설정에 모두 사용하세요.

