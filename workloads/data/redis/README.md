# Redis Replication & Sentinel (OT-CONTAINER-KIT Redis Operator)

이 디렉터리는 OT-CONTAINER-KIT에서 제공하는 `redis-operator`(CRDs: `redisredis.opstreelabs.in/v1beta2`)가
관리하는 두 개의 Custom Resource(`RedisReplication`, `RedisSentinel`)를 정의한다.

## 구성

- `base/redis-replication.yaml`: 공통 RedisReplication 스펙
- `base/redis-sentinel.yaml`: 상단 replication을 감시하는 Sentinel 스펙
- `overlays/dev/redis-failover.yaml`: dev 전용 패치(리소스, 10Gi PVC)
- `overlays/prod/redis-failover.yaml`: prod 전용 패치(리소스 상향, 50Gi PVC)

## CR 분리 이유

- OT-CONTAINER-KIT 오퍼레이터는 Spotahome과 CRD 스펙이 완전히 다르다.
  - `RedisFailover` → **미지원**
  - `RedisReplication`/`RedisSentinel`/`RedisCluster` 등으로 분리되어 있다.
- 따라서 Redis 데이터를 운영하려면 기존 `RedisFailover` CR을 **필수로 마이그레이션**해야 한다.

## 선행 조건

1. **Wave 25** `platform/helm/redis-operator` (Helm repo: `https://ot-container-kit.github.io/helm-charts`, chart `redis-operator`)
2. **Wave 35** 본 Kustomize 오버레이
3. **CA/네트워크**: Helm repo 접근 시 macOS 기본 CA(`/etc/ssl/cert.pem`)가 없으면 `--insecure-skip-tls-verify`가 필요하므로,
   `scripts/utilities/export-ca-env.sh`를 통해 사내 CA를 export하거나 chart를 미리 미러링한다.
4. **NetworkPolicy**: `tier=business-logic` → `redis` 네임스페이스 6379 포트 허용

## 배포 후 확인

```bash
kubectl get redisreplication -n redis
kubectl get redissentinel -n redis
kubectl get pods -n redis -l app.sesacthon.io/name=redis
```

## 참고
- OT-CONTAINER-KIT Redis Operator: https://github.com/OT-CONTAINER-KIT/redis-operator
- CRD 세부 스펙: `.tmp/redis-operator/crds/crds.yaml`

