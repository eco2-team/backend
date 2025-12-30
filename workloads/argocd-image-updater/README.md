# ArgoCD Image Updater 설정

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

### 1. DockerHub Secret (External Secret으로 자동 생성)

DockerHub 인증 정보는 External Secret으로 관리됩니다:
- 파일: `workloads/secrets/external-secrets/dev/dockerhub-pull-secret.yaml`
- Secret 이름: `dockerhub-credentials`
- Namespace: `argocd`
- 소스: AWS SSM (`/sesacthon/dev/dockerhub/username`, `/sesacthon/dev/dockerhub/password`)

ArgoCD가 External Secret CR을 sync하면 자동으로 생성됩니다.

### 2. Image Updater 설치

```bash
# Kustomize로 설치
kubectl apply -k workloads/argocd-image-updater/base/

# 또는 공식 매니페스트 직접 설치
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj-labs/argocd-image-updater/stable/manifests/install.yaml
```

### 3. 설치 확인

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
  argocd-image-updater.argoproj.io/image-list: canary=docker.io/mng990/eco2:auth-api-dev-canary

  # 업데이트 전략: digest (같은 태그라도 이미지 변경 시 업데이트)
  argocd-image-updater.argoproj.io/canary.update-strategy: digest

  # DockerHub 인증
  argocd-image-updater.argoproj.io/canary.pull-secret: pullsecret:argocd/dockerhub-credentials
```

### 업데이트 전략 옵션

| 전략 | 설명 | 사용 케이스 |
|------|------|------------|
| `digest` | 같은 태그라도 이미지 변경 시 업데이트 | **Canary (권장)** |
| `semver` | Semantic versioning 기반 최신 버전 | 정식 릴리즈 |
| `latest` | latest 태그의 최신 digest | 개발 환경 |
| `name` | 알파벳 순 최신 태그 | 특수 케이스 |

## 동작 원리

### digest 전략

1. CI가 `auth-api-dev-canary` 태그로 새 이미지 푸시
2. 이미지 digest가 변경됨 (예: `sha256:abc123` → `sha256:def456`)
3. Image Updater가 폴링 중 digest 변경 감지
4. ArgoCD Application refresh 트리거
5. Canary Deployment의 Pod 재생성 (새 이미지 pull)

### 폴링 주기

기본값: **2분** (configmap에서 변경 가능)

```yaml
# argocd-image-updater-config ConfigMap
data:
  check.interval: 2m  # 2분마다 레지스트리 확인
```

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
- [GitHub Repository](https://github.com/argoproj-labs/argocd-image-updater)
