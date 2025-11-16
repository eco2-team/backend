# Redis Failover (Spotahome Redis Operator)

이 디렉터리는 Spotahome Redis Operator가 관리하는 `RedisFailover` Custom Resource를 정의한다.

## 구조

- `base/redis-failover.yaml`: 공통 템플릿 (sentinel 3 replicas, redis 1 replica)
- `overlays/dev/`: Dev 환경 패치 (resources, storage 10Gi)
- `overlays/prod/`: Prod 환경 패치 (resources 증가, storage 50Gi)

## Sentinel vs Redis

- **Redis Pods**: 실제 데이터 저장 (replicas: 1, StatefulSet)
- **Sentinel Pods**: Master 모니터링 및 자동 Failover (replicas: 3, Deployment)
  - Quorum 기반 장애 감지 (2/3 이상 동의 필요)
  - 경량 프로세스 (128~256Mi)

## 선행 조건

- **Wave 25**: `platform/helm/redis-operator` (Operator)
- **Wave 35**: 이 CR 배포
- **NetworkPolicy**: `tier=business-logic` → `redis` 네임스페이스 허용 (6379 포트)

## 배포 후 확인

```bash
kubectl get redisfailover -n redis
kubectl get pods -n redis -l app.kubernetes.io/component=redis
kubectl get pods -n redis -l app.kubernetes.io/component=sentinel
```

## 참고
- Operator 스펙: `docs/architecture/operator/OPERATOR_SOURCE_SPEC.md`
- CRD 문서: https://github.com/spotahome/redis-operator

