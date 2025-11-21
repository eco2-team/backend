# Scan API Workload

Scan 도메인 API 서비스 Kustomize 구조.

## 구조

- `base/`: Deployment, Service, ConfigMap 기본 템플릿
- `overlays/dev/`: dev 환경 설정
- `overlays/prod/`: prod 환경 설정

## 환경 변수

- `POSTGRES_HOST`: `postgresql.postgres.svc.cluster.local`
- `REDIS_HOST`: `redis.redis.svc.cluster.local`

## 선행 조건

- Wave 35: Data Clusters
- Wave 58: `dockerhub-secret`

## 배포

```bash
kubectl apply -k workloads/domains/scan/overlays/dev
```
