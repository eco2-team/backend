# Auth API Workload

인증/권한 API 서비스 Kustomize 구조.

## 구조

- `base/`: Deployment, Service, ConfigMap 기본 템플릿
- `overlays/dev/`: dev 환경 (replicas: 1, debug: true, image tag: dev-latest)
- `overlays/prod/`: prod 환경 (replicas: 2, resources 증가, image tag: versioned)

## 환경 변수

- `POSTGRES_HOST`: `postgresql.postgres.svc.cluster.local`
- `REDIS_HOST`: `redis.redis.svc.cluster.local`
- ConfigMap: `LOG_LEVEL`, `ENVIRONMENT`
- Secret: `auth-secret` (DB credentials, JWT key 등)

## 선행 조건

- Wave 35: PostgreSQL/Redis Cluster (데이터 계층)
- Wave 58: `ghcr-secret` (GHCR pull secret, GitHub Actions에서 생성)
- NetworkPolicy: tier=business-logic → tier=data 허용

## 배포

```bash
kubectl apply -k workloads/apis/auth/overlays/dev
kubectl get pods -n auth
```

