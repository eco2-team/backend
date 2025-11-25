# Location API Workload

Location 도메인 API 서비스 Kustomize 구조.

## 구조

- `base/`: Deployment, Service, ConfigMap 기본 템플릿
- `overlays/dev/`: dev 환경 설정
- `overlays/prod/`: prod 환경 설정

### 부트스트랩 Job 순서

초기 배포 시 DB/데이터 시드를 위해 다음 Job 이 순차적으로 실행되며,
`argocd.argoproj.io/sync-wave`를 통해 `location-api` Deployment 보다 먼저 완료된다.

1. `location-db-bootstrap` (wave -30): cube/earthdistance 확장 설치 + location 스키마 생성
2. `location-normalized-import` (wave 10): 정규화 데이터셋을 DB에 직접 업서트 (PVC 미사용)

Job 이 성공하면 `Completed` 상태로 남고, 필요 시 `kubectl delete job <name>` 후 ArgoCD sync 를 재실행하면 다시 수행된다.

## 환경 변수

- `POSTGRES_HOST`: `postgresql.postgres.svc.cluster.local`
- `REDIS_HOST`: `redis.redis.svc.cluster.local`

## 선행 조건

- Wave 35: Data Clusters
- Wave 58: `dockerhub-secret`

## 배포

```bash
kubectl apply -k workloads/domains/location/overlays/dev
```
