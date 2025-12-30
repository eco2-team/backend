# ArgoCD Image Updater

Canary 이미지 자동 업데이트를 위한 ArgoCD Image Updater 설정입니다.

## 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                   Image Updater 동작 흐름                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. PR + canary 라벨 → CI가 {service}-dev-canary 이미지 빌드    │
│                    ↓                                             │
│  2. DockerHub에 같은 태그로 푸시 (digest 변경)                   │
│                    ↓                                             │
│  3. Image Updater가 2분마다 DockerHub 폴링                       │
│                    ↓                                             │
│  4. digest 변경 감지 → ArgoCD Application 업데이트 트리거        │
│                    ↓                                             │
│  5. ArgoCD가 자동 sync → Canary Pod 재생성                       │
│                    ↓                                             │
│  6. 새 Canary 이미지로 자동 배포 완료!                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 설치 방법

### ArgoCD Application으로 배포 (권장)

Image Updater는 ArgoCD Application으로 관리됩니다:

```yaml
# clusters/dev/apps/06-argocd-image-updater.yaml
source:
  repoURL: https://argoproj.github.io/argo-helm
  chart: argocd-image-updater
  targetRevision: 0.11.0
```

ArgoCD가 자동으로 배포하므로 별도 설치 불필요합니다.

### DockerHub Secret (External Secret으로 자동 생성)

DockerHub 인증 정보는 External Secret으로 관리됩니다:
- 파일: `workloads/secrets/external-secrets/dev/dockerhub-pull-secret.yaml`
- Secret 이름: `dockerhub-credentials`
- Namespace: `argocd`
- 소스: AWS SSM (`/sesacthon/dev/dockerhub/username`, `/sesacthon/dev/dockerhub/password`)

### 설치 확인

```bash
# Deployment 확인
kubectl get deployment -n argocd argocd-image-updater

# 로그 확인
kubectl logs -n argocd deployment/argocd-image-updater -f
```

## Application Annotation

ApplicationSet에 다음 annotation이 추가되어 있습니다:

```yaml
annotations:
  # 이미지 목록 (별칭=이미지:태그)
  argocd-image-updater.argoproj.io/image-list: stable=docker.io/mng990/eco2:auth-api-dev-latest,canary=docker.io/mng990/eco2:auth-api-dev-canary

  # 업데이트 전략: digest (같은 태그라도 이미지 변경 시 업데이트)
  argocd-image-updater.argoproj.io/stable.update-strategy: digest
  argocd-image-updater.argoproj.io/canary.update-strategy: digest

  # DockerHub 인증
  argocd-image-updater.argoproj.io/stable.pull-secret: pullsecret:argocd/dockerhub-credentials
  argocd-image-updater.argoproj.io/canary.pull-secret: pullsecret:argocd/dockerhub-credentials
```

### 업데이트 전략 옵션

| 전략 | 설명 | 사용 케이스 |
|------|------|------------|
| `digest` | 같은 태그라도 이미지 변경 시 업데이트 | **Stable/Canary (권장)** |
| `semver` | Semantic versioning 기반 최신 버전 | 정식 릴리즈 |
| `latest` | latest 태그의 최신 digest | 개발 환경 |
| `name` | 알파벳 순 최신 태그 | 특수 케이스 |

## 트러블슈팅

### 로그 확인

```bash
# Image Updater 로그
kubectl logs -n argocd deployment/argocd-image-updater -f

# 특정 Application 관련 로그
kubectl logs -n argocd deployment/argocd-image-updater | grep "dev-api-auth"
```

### 수동 트리거

```bash
# Application 강제 refresh
kubectl annotate application dev-api-auth -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite
```

### 이미지 업데이트 확인

```bash
# 현재 이미지 digest 확인
kubectl get pod -n auth -l version=v2 -o jsonpath='{.items[0].status.containerStatuses[0].imageID}'
```

## 참고 자료

- [ArgoCD Image Updater 공식 문서](https://argocd-image-updater.readthedocs.io/)
- [Helm Chart](https://github.com/argoproj/argo-helm/tree/main/charts/argocd-image-updater)
- [GitHub Repository](https://github.com/argoproj-labs/argocd-image-updater)
